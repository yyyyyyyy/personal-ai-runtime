"""Mail context fragments.

从旧 prompts.py + skills.py 提取认知内容，重构为 ContextFragment 实现。
Fragment 只负责数据收集，不负责推理或 UI 呈现。
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field

from app.context_runtime import ContextFragment, FragmentResult, RuntimeContext
from app.core.runtime import read_ports

_CATEGORY_LABELS = {
    "important": "重要",
    "actionable": "待办",
    "ignorable": "信息",
}

_UNREAD_STATUSES = frozenset({"unread", "pending", "new"})

# Phrases stripped before keyword extraction (mail intent / filler).
_MAIL_NOISE_PHRASES = tuple(
    sorted(
        {
            "回复邮件",
            "查邮件",
            "收件箱",
            "有没有",
            "帮我",
            "帮忙",
            "一下",
            "看看",
            "查看",
            "查找",
            "搜索",
            "找一下",
            "查一下",
            "邮件",
            "发信",
            "回复",
            "关于",
            "相关",
            "最近",
            "所有",
            "全部",
            "上周",
            "本周",
            "今天",
            "昨天",
            "明天",
            "please",
            "emails",
            "email",
            "inbox",
            "gmail",
            "mail",
            "check",
            "find",
            "search",
            "show",
            "list",
            "look",
            "help",
            "about",
            "from",
            "reply",
            "send",
            "read",
            "unread",
        },
        key=len,
        reverse=True,
    )
)

_MAIL_STOPWORDS = frozenset(
    {
        "的",
        "了",
        "吗",
        "呢",
        "吧",
        "啊",
        "请",
        "我",
        "你",
        "有",
        "和",
        "与",
        "或",
        "在",
        "是",
        "什么",
        "哪些",
        "一下",
        "the",
        "a",
        "an",
        "of",
        "for",
        "to",
        "me",
        "my",
        "and",
        "or",
        "is",
        "are",
        "with",
    }
)


def extract_mail_search_terms(message: str) -> list[str]:
    """Extract searchable terms from a conversational mail request.

    Returns [] when the message is only intent filler (e.g. "查一下邮件"),
    so EmailSearchFragment can skip a useless full-sentence LIKE query.
    """
    text = (message or "").strip()
    if not text:
        return []

    terms: list[str] = []

    for email in re.findall(r"[\w.+-]+@[\w.-]+\.\w+", text):
        terms.append(email)
        text = text.replace(email, " ")

    for quoted in re.findall(r"[「『\"']([^「『\"']+)[」』\"']", text):
        q = quoted.strip()
        if q:
            terms.append(q)
            text = text.replace(quoted, " ", 1)

    lowered = text
    for phrase in _MAIL_NOISE_PHRASES:
        if re.fullmatch(r"[A-Za-z]+", phrase):
            lowered = re.sub(rf"\b{re.escape(phrase)}\b", " ", lowered, flags=re.IGNORECASE)
        else:
            lowered = lowered.replace(phrase, " ")

    for tok in re.findall(r"[A-Za-z][A-Za-z0-9._-]{2,}", lowered):
        if tok.lower() not in _MAIL_STOPWORDS and tok.lower() not in {t.lower() for t in terms}:
            terms.append(tok)

    for tok in re.findall(r"[\u4e00-\u9fff]{2,}", lowered):
        pieces = [
            part
            for part in re.split(r"[的了吗呢吧啊和与找发给]", tok)
            if len(part) >= 2 and part not in _MAIL_STOPWORDS
        ]
        if pieces:
            for part in pieces:
                if part not in terms:
                    terms.append(part)
            continue
        cleaned = tok.strip("的了吗呢吧啊")
        if len(cleaned) >= 2 and cleaned not in _MAIL_STOPWORDS and cleaned not in terms:
            terms.append(cleaned)

    # Prefer more specific tokens first; cap to keep LIKE queries tight.
    terms.sort(key=lambda t: ("@" not in t, -len(t), t))
    deduped: list[str] = []
    seen: set[str] = set()
    for t in terms:
        key = t.lower()
        if key in seen:
            continue
        seen.add(key)
        deduped.append(t)
    return deduped[:5]


def _format_date(row: dict) -> str:
    raw = str(row.get("received_at") or row.get("created_at") or "").strip()
    return raw[:10] if raw else "日期未知"


def _format_preview(row: dict, *, max_len: int = 60) -> str:
    preview = str(row.get("preview") or "").strip()
    if not preview:
        return ""
    preview = re.sub(r"\s+", " ", preview)
    if len(preview) > max_len:
        return preview[: max_len - 1] + "…"
    return preview


def _format_email_line(row: dict, *, include_category: bool = True) -> str:
    tags: list[str] = []
    if include_category:
        label = _CATEGORY_LABELS.get(str(row.get("category") or ""), "")
        if label:
            tags.append(label)
    status = str(row.get("status") or "").lower()
    if status in _UNREAD_STATUSES:
        tags.append("未读" if status != "pending" else "待处理")

    tag_prefix = f"[{'|'.join(tags)}] " if tags else ""
    sender = str(row.get("sender") or "未知发件人").strip() or "未知发件人"
    subject = str(row.get("subject") or "(无主题)").strip() or "(无主题)"
    line = f"- {tag_prefix}{sender}: {subject} ({_format_date(row)})\n  id: {row.get('id')}"
    preview = _format_preview(row)
    if preview:
        line += f"\n  {preview}"
    return line


def _email_sources(rows: list[dict]) -> list[dict]:
    sources: list[dict] = []
    for row in rows:
        email_id = str(row.get("id") or "").strip()
        if not email_id:
            continue
        title = str(row.get("subject") or email_id)
        sources.append({"id": email_id, "type": "email", "title": title})
    return sources


def _search_by_terms(terms: list[str], *, limit: int) -> list[dict]:
    """AND semantics across terms: keep ids present in every term result."""
    if not terms:
        return []

    per_term: list[list[dict]] = []
    for term in terms:
        rows = read_ports.search_inbox_emails(term, limit=limit)
        if not rows:
            return []
        per_term.append(rows)

    if len(per_term) == 1:
        return per_term[0][:limit]

    id_sets = [{str(r.get("id")) for r in rows if r.get("id")} for rows in per_term]
    common_ids = set.intersection(*id_sets) if id_sets else set()
    if not common_ids:
        # Fall back to the most specific term's hits when AND is empty.
        return per_term[0][:limit]

    # Preserve ranking from the most specific (first) term.
    ordered = [r for r in per_term[0] if str(r.get("id")) in common_ids]
    return ordered[:limit]


@dataclass
class RecentEmailsFragment(ContextFragment):
    """收集最近收件箱邮件的列表（含邮件助手角色定义）。"""

    id: str = field(default="mail.recent_emails", init=False)
    priority: int = field(default=70, init=False)
    max_tokens: int = field(default=1800, init=False)
    tags: frozenset[str] = field(default_factory=lambda: frozenset({"mail"}), init=False)

    _IDENTITY = (
        "You are a Mail assistant within the Personal AI Runtime.\n"
        "Scope: search/read/summarize/draft/send emails, extract tasks.\n"
        "Be precise, concise, and governance-aware.\n"
    )

    async def collect(self, ctx: RuntimeContext) -> FragmentResult:
        # When the user is searching for something specific, keep recent slim
        # to avoid overlapping the search fragment.
        search_terms = extract_mail_search_terms(ctx.user_message or "")
        limit = 8 if search_terms else 12

        try:
            rows = read_ports.query_recent_inbox_emails(
                limit=limit,
                order="importance_desc",
            )
        except Exception:
            return FragmentResult(content=self._IDENTITY)

        if not rows:
            return FragmentResult(content=self._IDENTITY + "\n收件箱为空。")

        lines = [self._IDENTITY, "## 最近邮件\n"]
        lines.extend(_format_email_line(r, include_category=True) for r in rows)
        return FragmentResult(content="\n".join(lines), sources=_email_sources(rows))


@dataclass
class EmailSearchFragment(ContextFragment):
    """按用户消息关键词搜索邮件（mail 标签触发）。"""

    id: str = field(default="mail.email_search", init=False)
    priority: int = field(default=65, init=False)
    max_tokens: int = field(default=1500, init=False)
    tags: frozenset[str] = field(default_factory=lambda: frozenset({"mail"}), init=False)

    async def collect(self, ctx: RuntimeContext) -> FragmentResult:
        terms = extract_mail_search_terms(ctx.user_message or "")
        if not terms:
            return FragmentResult(content="")

        try:
            rows = _search_by_terms(terms, limit=15)
        except Exception:
            return FragmentResult(content="")

        if not rows:
            return FragmentResult(content="")

        label = " ".join(terms)
        lines = [f'## 搜索结果: "{label}"\n']
        lines.extend(_format_email_line(r, include_category=True) for r in rows)
        return FragmentResult(content="\n".join(lines), sources=_email_sources(rows))
