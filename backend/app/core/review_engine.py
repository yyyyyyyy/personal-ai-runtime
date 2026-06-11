"""Review Engine — generates Daily, Weekly, and Monthly reviews.

Review is the key value-producing component: it analyzes events, summarizes progress,
detects problems, and suggests adjustments. Reviews complete the Goal→Action→Event→Memory→Review→Goal loop.

LLM polish is enabled by default (REVIEW_NARRATIVE_LLM_ENABLED=true). The sync API
(polish_narrative) wraps asyncio internally for APScheduler compatibility.
"""

import asyncio
import json
import logging
import uuid
from datetime import UTC, datetime, timedelta

from app.core.agents.memory_engine import memory_engine
from app.core.runtime.legacy_event_adapter import to_legacy_dict
from app.core.runtime.projection.narrative_audit import build_narrative_audit
from app.core.runtime.projection.narrative_polish import polish_narrative_async
from app.core.telemetry.event_recorder import event_recorder

logger = logging.getLogger(__name__)


def _kernel():
    from app.core.runtime import kernel_instance

    return kernel_instance.kernel


def _db():
    from app.store import database

    return database.db

# Identity RFC N5 — narrative is projection, not ratified identity.
REVIEW_PROJECTION_META: dict = {
    "projection": True,
    "projection_type": "identity_narrative_surface",
    "interpretive_plurality": True,
    "not_ratified": True,
}

_PROJECTION_PREAMBLE = (
    "> 以下为系统投影草稿（Identity Projection），不代表对你身份的认定；"
    "竞争解释可能并存。"
)


class ReviewEngine:
    """Generates periodic reviews by aggregating events and querying state."""

    def generate_daily_review(self, date: str | None = None) -> str:
        """Generate a daily review for the given date (default: today)."""
        if date is None:
            date = datetime.now().strftime("%Y-%m-%d")

        with _db().get_db() as conn:
            existing = conn.execute(
                "SELECT id FROM reviews WHERE type = 'daily' AND period_start = ? LIMIT 1",
                (date,),
            ).fetchone()
        if existing:
            return existing["id"]

        events = self._get_events_for_date(date)
        goals = self._get_active_goals()
        stagnant = self._get_stagnant_goals()

        review_id = str(uuid.uuid4())
        content = self._finalize_review_content(
            self._build_review_content("daily", date, date, events, goals, stagnant),
            events,
        )
        key_insights = self._key_insights_payload(content, surface="daily_review", events=events)

        with _db().get_db() as conn:
            conn.execute(
                "INSERT INTO reviews (id, type, period_start, period_end, content, key_insights, created_at) "
                "VALUES (?, 'daily', ?, ?, ?, ?, ?)",
                (review_id, date, date, content, key_insights,
                 datetime.now(UTC).isoformat()),
            )

        # Store key findings as memories
        if stagnant:
            for g in stagnant[:2]:
                memory_engine.store_memory(
                    f"目标「{g['title']}」已停滞超过3天，需要重新评估或采取行动",
                    category="fact",
                    source=f"daily_review_{date}",
                    actor="kernel",
                )

        return review_id

    def generate_weekly_review(self) -> str:
        """Generate a weekly review for the past 7 days."""
        end_date = datetime.now()
        start_date = end_date - timedelta(days=7)

        events = self._get_events_for_period(start_date.strftime("%Y-%m-%d"), end_date.strftime("%Y-%m-%d"))
        goals = self._get_active_goals()
        completed = self._get_completed_goals(start_date.strftime("%Y-%m-%d"))

        review_id = str(uuid.uuid4())
        content = self._finalize_review_content(
            self._build_review_content(
                "weekly", start_date.strftime("%Y-%m-%d"), end_date.strftime("%Y-%m-%d"),
                events, goals, completed,
            ),
            events,
        )
        key_insights = self._key_insights_payload(content, surface="weekly_review", events=events)

        with _db().get_db() as conn:
            conn.execute(
                "INSERT INTO reviews (id, type, period_start, period_end, content, key_insights, created_at) "
                "VALUES (?, 'weekly', ?, ?, ?, ?, ?)",
                (review_id, start_date.strftime("%Y-%m-%d"), end_date.strftime("%Y-%m-%d"),
                 content, key_insights, datetime.now(UTC).isoformat()),
            )

        return review_id

    def generate_monthly_review(self) -> str:
        """Generate a monthly review for the past 30 days."""
        end_date = datetime.now()
        start_date = end_date - timedelta(days=30)

        events = self._get_events_for_period(start_date.strftime("%Y-%m-%d"), end_date.strftime("%Y-%m-%d"))
        goals = self._get_active_goals()
        completed = self._get_completed_goals(start_date.strftime("%Y-%m-%d"))

        review_id = str(uuid.uuid4())
        content = self._finalize_review_content(
            self._build_review_content(
                "monthly", start_date.strftime("%Y-%m-%d"), end_date.strftime("%Y-%m-%d"),
                events, goals, completed,
            ),
            events,
        )
        key_insights = self._key_insights_payload(content, surface="monthly_review", events=events)

        with _db().get_db() as conn:
            conn.execute(
                "INSERT INTO reviews (id, type, period_start, period_end, content, key_insights, created_at) "
                "VALUES (?, 'monthly', ?, ?, ?, ?, ?)",
                (review_id, start_date.strftime("%Y-%m-%d"), end_date.strftime("%Y-%m-%d"),
                 content, key_insights, datetime.now(UTC).isoformat()),
            )

        return review_id

    def _get_events_for_date(self, date: str) -> list[dict]:
        return self._get_events_for_period(date, date)

    def _get_events_for_period(self, start: str, end: str) -> list[dict]:
        """Governed events via kernel.read_events; application events via event_recorder."""
        since_ts = f"{start}T00:00:00"
        end_ts = f"{end}T23:59:59.999999"

        kernel_rows = [
            to_legacy_dict(e)
            for e in _kernel().read_events(since_ts=since_ts, limit=5000, order="asc")
            if (e.ts or "") <= end_ts
        ]

        span_days = max(
            (datetime.fromisoformat(end) - datetime.fromisoformat(start)).days + 1,
            1,
        )
        app_rows = event_recorder.get_recent_events(days=span_days + 1, limit=5000)
        app_rows = [
            row for row in app_rows
            if row.get("type") != "conversation"
            and start <= (row.get("timestamp") or "")[:10] <= end
        ]

        merged = kernel_rows + app_rows
        merged.sort(key=lambda r: r.get("timestamp", ""))
        return merged

    def _get_active_goals(self) -> list[dict]:
        return _kernel().query_state(
            "goals", status="active", order="importance_urgency_desc", limit=500
        )

    def _get_stagnant_goals(self) -> list[dict]:
        return _kernel().query_state(
            "goals",
            status="active",
            last_activity_older_than_days=3,
            order="last_activity_asc",
            limit=500,
        )

    def _get_completed_goals(self, since: str) -> list[dict]:
        return _kernel().query_state(
            "goals", status="completed", updated_since=since, limit=500
        )

    def _build_review_content(
        self, review_type: str, start: str, end: str,
        events: list[dict], goals: list[dict], extra: list[dict]
    ) -> str:
        """Build a structured review content string (template-based, for LLM to polish)."""

        period_label = {
            "daily": f"日期: {start}",
            "weekly": f"周期: {start} ~ {end}",
            "monthly": f"周期: {start} ~ {end}",
        }.get(review_type, "")

        lines = [
            f"# {review_type.upper()} 复盘\n",
            _PROJECTION_PREAMBLE,
            "",
            period_label,
            "",
        ]

        # Event summary
        lines.append("## 事件摘要")
        events_by_type = {}
        for e in events:
            t = e["type"]
            events_by_type.setdefault(t, 0)
            events_by_type[t] += 1

        for t, count in events_by_type.items():
            lines.append(f"- {t}: {count} 条")
        lines.append(f"\n总计: {len(events)} 条事件")
        lines.append("")

        # Goal progress
        lines.append("## 目标进展")
        if goals:
            for g in goals:
                lines.append(f"- [{g['status']}] {g['title']}")
                if g.get("deadline"):
                    lines.append(f"  截止日期: {g['deadline']}")
        else:
            lines.append("暂无活跃目标")
        lines.append("")

        # Stagnant goals (for daily review)
        if review_type == "daily" and extra:
            lines.append("## ⚠️ 停滞目标")
            for g in extra:
                days = "未知"
                if g.get("last_activity_at"):
                    delta = datetime.now() - datetime.fromisoformat(g["last_activity_at"])
                    days = f"{delta.days}天"
                lines.append(f"- {g['title']} (停滞 {days})")
            lines.append("")

        # Completed goals (for weekly/monthly)
        if review_type in ("weekly", "monthly") and extra:
            lines.append("## ✅ 已完成目标")
            for g in extra:
                lines.append(f"- {g['title']}")
            lines.append("")

        self._append_trajectory_plurality_section(lines)

        # Suggestions
        lines.append("## AI 建议")
        lines.append("(将由 LLM 根据以上数据生成个性化建议；属系统假设，非身份认定)")
        lines.append("")

        return "\n".join(lines)

    def _append_trajectory_plurality_section(self, lines: list[str]) -> None:
        """Identity RFC N4 — competing continuity interpretations remain visible."""
        try:
            trajectories = _kernel().list_trajectories()
        except Exception:
            return
        active = [
            t for t in trajectories
            if t.get("status", "active") == "active"
            and t.get("claim_status") != "released"
        ]
        released = [
            t for t in trajectories
            if t.get("status") == "released" or t.get("claim_status") == "released"
        ]
        if not active and not released:
            return
        lines.append("## 轨迹视角（连续性假说，可争议）")
        for t in active[:8]:
            tid = t.get("id", "")
            desc = t.get("description", tid)
            competing = t.get("competing_with") or []
            opt = t.get("identity_narrative_opt_in")
            opt_label = "已授权身份叙事" if opt else "未授权身份叙事"
            line = f"- {tid}: {desc} [{opt_label}]"
            if competing:
                line += f" （竞争轨迹: {', '.join(competing[:3])}）"
            lines.append(line)
        if released:
            lines.append("")
            lines.append("### 已放下轨迹（墓碑，不再定义身份叙事）")
            for t in released[:8]:
                tid = t.get("id", "")
                desc = t.get("description", tid)
                lines.append(
                    f"- [已放下] {tid}: {desc}（Release；结构保留，影响已解除）"
                )
        lines.append("")

    def _finalize_review_content(
        self, content: str, events: list[dict]
    ) -> str:
        k = _kernel()
        try:
            trajectories = k.list_trajectories()
        except Exception:
            return content
        memories = k.query_state("memories", limit=300)
        link_seqs: dict[str, list[int]] = {}
        for t in trajectories:
            tid = t.get("id")
            if not tid:
                continue
            try:
                data = k.query_trajectory(tid)
                if data:
                    link_seqs[tid] = [
                        int(lnk["event_seq"])
                        for lnk in data.get("links", [])
                        if lnk.get("event_seq") is not None
                    ]
            except Exception:
                link_seqs[tid] = []
        released_ids = {
            t["id"]
            for t in trajectories
            if t.get("id")
            and (t.get("status") == "released" or t.get("claim_status") == "released")
        }
        return asyncio.run(
            polish_narrative_async(
                content,
                trajectories=trajectories,
                memories=memories,
                events=events,
                trajectory_link_seqs=link_seqs,
                released_trajectory_ids=released_ids,
            )
        )

    def _key_insights_payload(
        self, content: str, *, surface: str, events: list[dict] | None = None
    ) -> str:
        k = _kernel()
        try:
            trajectories = k.list_trajectories()
        except Exception:
            trajectories = []
        memories = k.query_state("memories", limit=300)
        link_seqs: dict[str, list[int]] = {}
        for t in trajectories:
            tid = t.get("id")
            if not tid:
                continue
            try:
                data = k.query_trajectory(tid)
                if data:
                    link_seqs[tid] = [
                        int(lnk["event_seq"])
                        for lnk in data.get("links", [])
                        if lnk.get("event_seq") is not None
                    ]
            except Exception:
                link_seqs[tid] = []
        audit = build_narrative_audit(
            content,
            trajectories,
            memories=memories,
            events=events or [],
            trajectory_link_seqs=link_seqs,
        )
        payload = {
            **REVIEW_PROJECTION_META,
            "surface": surface,
            "insights": self._extract_insights(content),
            "narrative_audit": audit,
        }
        return json.dumps(payload, ensure_ascii=False)

    @staticmethod
    def parse_key_insights(raw: str | None) -> dict:
        """Normalize key_insights from DB (legacy list or projection object)."""
        if not raw:
            return {}
        try:
            data = json.loads(raw)
        except json.JSONDecodeError:
            return {"insights": [], "raw": raw}
        if isinstance(data, list):
            return {"insights": data, "projection": False, "legacy": True}
        return data

    def _extract_insights(self, content: str) -> list[str]:
        """Extract key insights from review content (simplified heuristic version)."""
        insights = []
        if "停滞目标" in content:
            insights.append("存在停滞目标，需要关注")
        if "已完成目标" in content:
            insights.append("有已完成的目标")
        return insights

    def list_reviews(self, limit: int = 10) -> list[dict]:
        with _db().get_db() as conn:
            rows = conn.execute(
                "SELECT * FROM reviews ORDER BY created_at DESC LIMIT ?", (limit,)
            ).fetchall()
        out = []
        for r in rows:
            item = dict(r)
            item["key_insights_parsed"] = self.parse_key_insights(item.get("key_insights"))
            out.append(item)
        return out

    def get_review(self, review_id: str) -> dict | None:
        with _db().get_db() as conn:
            row = conn.execute(
                "SELECT * FROM reviews WHERE id = ?", (review_id,)
            ).fetchone()
        if not row:
            return None
        item = dict(row)
        item["key_insights_parsed"] = self.parse_key_insights(item.get("key_insights"))
        return item


review_engine = ReviewEngine()
