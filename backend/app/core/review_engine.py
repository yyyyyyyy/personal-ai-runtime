"""Review Engine — generates Daily, Weekly, and Monthly reviews.

Review is the key value-producing component: it analyzes events, summarizes progress,
detects problems, and suggests adjustments. Reviews complete the Goal→Action→Event→Memory→Review→Goal loop.

LLM polish is enabled by default (REVIEW_NARRATIVE_LLM_ENABLED=true). The sync API
(polish_narrative) wraps asyncio internally for APScheduler compatibility.
"""

import json
import logging
import re
import uuid
from datetime import UTC, datetime, timedelta

from app.config import settings
from app.core.agents.llm_router import llm_router
from app.core.agents.memory_engine import memory_engine
from app.core.runtime.egress.egress_gate import prepare_llm_egress
from app.core.runtime.legacy_event_adapter import to_legacy_dict
from app.core.telemetry.event_recorder import event_recorder

logger = logging.getLogger(__name__)

_REVIEW_POLISH_SYSTEM = (
    "你是个人复盘助手。在保留结构与事实的前提下润色下文，使其更流畅易读。"
    "不要添加不存在的事实。"
)

_REVIEW_SUGGESTIONS_SYSTEM = (
    "你是个人复盘助手。根据以下复盘内容，生成 3-5 条具体、可执行的个性化建议。"
    "使用简洁的中文 bullet points（以 - 开头），不要重复原文，不要添加不存在的事实。"
)

_AI_SUGGESTIONS_MARKER = "## AI 建议"
_AI_SUGGESTIONS_HEADING_RE = re.compile(r"(?m)^#{1,3}\s*AI 建议\s*$")
_PLACEHOLDER_SUGGESTIONS = "将由 LLM 根据以上数据生成个性化建议"


def _kernel():
    from app.core.runtime import kernel_instance

    return kernel_instance.kernel


def _db():
    from app.store import database

    return database.db


async def _polish_review_async(content: str) -> str:
    """Polish review narrative via LLM; fall back to template on error."""
    if not settings.review_narrative_llm_enabled or not content.strip():
        return content
    try:
        client, provider = llm_router.get_client()
        messages = [
            {"role": "system", "content": _REVIEW_POLISH_SYSTEM},
            {"role": "user", "content": content},
        ]
        messages, _audit = prepare_llm_egress(messages, purpose="review_narrative")
        response = await client.chat.completions.create(
            model=provider.model,
            messages=messages,  # type: ignore[arg-type]
            temperature=0.4,
            max_tokens=settings.llm_max_tokens,
        )
        polished = (response.choices[0].message.content or "").strip()
        return polished or content
    except Exception as exc:
        logger.warning("review polish LLM failed: %s", exc)
        return content


async def _generate_ai_suggestions_async(content: str) -> str:
    """Generate personalized review suggestions via LLM."""
    if not settings.review_narrative_llm_enabled or not content.strip():
        return "暂无足够数据生成建议。"
    try:
        client, provider = llm_router.get_client()
        messages = [
            {"role": "system", "content": _REVIEW_SUGGESTIONS_SYSTEM},
            {"role": "user", "content": content},
        ]
        messages, _audit = prepare_llm_egress(messages, purpose="review_suggestions")
        response = await client.chat.completions.create(
            model=provider.model,
            messages=messages,  # type: ignore[arg-type]
            temperature=0.5,
            max_tokens=min(settings.llm_max_tokens, 800),
        )
        suggestions = (response.choices[0].message.content or "").strip()
        return suggestions or "暂无足够数据生成建议。"
    except Exception as exc:
        logger.warning("review suggestions LLM failed: %s", exc)
        return "建议生成失败，请稍后重试。"


class ReviewEngine:
    """Generates periodic reviews by aggregating events and querying state."""

    async def generate_daily_review(self, date: str | None = None) -> str:
        """Generate a daily review for the given date (default: today)."""
        if date is None:
            date = datetime.now().strftime("%Y-%m-%d")

        with _db().get_db() as conn:
            existing = conn.execute(
                "SELECT id FROM reviews WHERE type = 'daily' AND period_start = ? LIMIT 1",
                (date,),
            ).fetchone()
        if existing:
            return await self._ensure_ai_suggestions(existing["id"])

        events = self._get_events_for_date(date)
        goals = self._get_active_goals()
        stagnant = self._get_stagnant_goals()

        review_id = str(uuid.uuid4())
        content = await self._finalize_review_content(
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

    async def generate_weekly_review(self) -> str:
        """Generate a weekly review for the past 7 days."""
        end_date = datetime.now()
        start_date = end_date - timedelta(days=7)

        events = self._get_events_for_period(start_date.strftime("%Y-%m-%d"), end_date.strftime("%Y-%m-%d"))
        goals = self._get_active_goals()
        completed = self._get_completed_goals(start_date.strftime("%Y-%m-%d"))

        review_id = str(uuid.uuid4())
        content = await self._finalize_review_content(
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

    async def generate_monthly_review(self) -> str:
        """Generate a monthly review for the past 30 days."""
        end_date = datetime.now()
        start_date = end_date - timedelta(days=30)

        events = self._get_events_for_period(start_date.strftime("%Y-%m-%d"), end_date.strftime("%Y-%m-%d"))
        goals = self._get_active_goals()
        completed = self._get_completed_goals(start_date.strftime("%Y-%m-%d"))

        review_id = str(uuid.uuid4())
        content = await self._finalize_review_content(
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

        # Suggestions section — content filled in by _finalize_review_content
        lines.append(_AI_SUGGESTIONS_MARKER)
        lines.append("")

        return "\n".join(lines)

    def _split_before_suggestions(self, content: str) -> tuple[str, bool]:
        match = _AI_SUGGESTIONS_HEADING_RE.search(content)
        if not match:
            return content.rstrip(), False
        return content[: match.start()].rstrip(), True

    async def _ensure_ai_suggestions(self, review_id: str) -> str:
        """Refresh AI suggestions for an existing review when still using placeholder text."""
        review = self.get_review(review_id)
        if not review:
            return review_id

        content = review.get("content", "")
        _, has_section = self._split_before_suggestions(content)
        needs_refresh = _PLACEHOLDER_SUGGESTIONS in content
        if not needs_refresh and has_section:
            after = _AI_SUGGESTIONS_HEADING_RE.split(content, maxsplit=1)[-1].strip()
            needs_refresh = not after or after.startswith("(") or _PLACEHOLDER_SUGGESTIONS in after

        if not needs_refresh:
            return review_id

        updated = await self._finalize_review_content(content, [])
        surface = f"{review.get('type', 'daily')}_review"
        key_insights = self._key_insights_payload(updated, surface=surface)

        with _db().get_db() as conn:
            conn.execute(
                "UPDATE reviews SET content = ?, key_insights = ? WHERE id = ?",
                (updated, key_insights, review_id),
            )
        return review_id

    async def _finalize_review_content(
        self, content: str, events: list[dict]
    ) -> str:
        del events  # reserved for future context-aware generation
        base, has_section = self._split_before_suggestions(content)
        if has_section:
            polished_base = await _polish_review_async(base)
            suggestions = await _generate_ai_suggestions_async(polished_base)
            return f"{polished_base}\n\n{_AI_SUGGESTIONS_MARKER}\n{suggestions}\n"
        return await _polish_review_async(content)

    def _key_insights_payload(
        self, content: str, *, surface: str, events: list[dict] | None = None
    ) -> str:
        del events
        payload = {
            "surface": surface,
            "insights": self._extract_insights(content),
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
        match = _AI_SUGGESTIONS_HEADING_RE.search(content)
        if match:
            suggestions = content[match.end():]
            for line in suggestions.splitlines():
                line = line.strip()
                if line.startswith("- "):
                    insights.append(line[2:].strip())
        return insights[:5]

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
