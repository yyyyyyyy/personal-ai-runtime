"""Mail context fragments.

从旧 prompts.py + skills.py 提取认知内容，重构为 ContextFragment 实现。
Fragment 只负责数据收集，不负责推理或 UI 呈现。
"""

from __future__ import annotations

from dataclasses import dataclass, field

from app.context_runtime import ContextFragment, FragmentResult, RuntimeContext
from app.core.runtime import read_ports


@dataclass
class RecentEmailsFragment(ContextFragment):
    """收集最近收件箱邮件的列表（含邮件助手角色定义）。"""

    id: str = field(default="mail.recent_emails", init=False)

    _IDENTITY = (
        "You are a Mail assistant within the Personal AI Runtime.\n"
        "Scope: search/read/summarize/draft/send emails, extract tasks.\n"
        "Be precise, concise, and governance-aware.\n"
    )

    async def collect(self, ctx: RuntimeContext) -> FragmentResult:
        rows = read_ports.query_recent_inbox_emails(limit=20)

        if not rows:
            return FragmentResult(content=self._IDENTITY + "\n收件箱为空。")

        lines = [self._IDENTITY, "## 最近邮件\n"]
        for r in rows:
            cat = r.get("category") or ""
            category_label = {"important": "重要", "actionable": "待办", "ignorable": "信息"}.get(
                cat, cat
            )
            date_val = r.get("received_at") or r.get("created_at") or ""
            sender = r.get("sender") or r.get("from") or ""
            lines.append(
                f"- [{category_label}] {sender}: {r.get('subject')} ({str(date_val)[:10]})\n"
                f"  id: {r.get('id')}"
            )

        return FragmentResult(content="\n".join(lines))


@dataclass
class EmailSearchFragment(ContextFragment):
    """按用户消息关键词搜索邮件（mail 标签触发）。"""

    id: str = field(default="mail.email_search", init=False)

    async def collect(self, ctx: RuntimeContext) -> FragmentResult:
        query = (ctx.user_message or "").strip()
        if not query:
            return FragmentResult(content="")

        rows = read_ports.search_inbox_emails(query, limit=30)

        if not rows:
            return FragmentResult(content="")

        lines = [f'## 搜索结果: "{query}"\n']
        for r in rows:
            date_val = r.get("received_at") or r.get("created_at") or ""
            sender = r.get("sender") or r.get("from") or ""
            lines.append(
                f"- {sender}: {r.get('subject')} ({str(date_val)[:10]})\n"
                f"  id: {r.get('id')}"
            )

        return FragmentResult(content="\n".join(lines))
