"""Tool post-processing registry — App-specific LLM context shaping per capability.

Keeps Brain generic; product rules (e.g. inbox table UI) live here.
"""

from __future__ import annotations

import json
from collections.abc import Callable
from dataclasses import dataclass

CompactFn = Callable[[str], str]
CannedSummaryFn = Callable[[list[dict], list[dict]], str | None]
PromptHintFn = Callable[[], str]


@dataclass
class ToolPostprocessRule:
    compact_for_llm: CompactFn | None = None
    canned_summary: CannedSummaryFn | None = None
    prompt_hint: PromptHintFn | None = None


_RULES: dict[str, ToolPostprocessRule] = {}


def register_rule(tool_name: str, rule: ToolPostprocessRule) -> None:
    _RULES[tool_name] = rule


def compact_for_llm(tool_name: str, content: str) -> str:
    rule = _RULES.get(tool_name)
    if rule and rule.compact_for_llm:
        return rule.compact_for_llm(content)
    return content


def canned_summary(tool_calls: list[dict], tool_results: list[dict]) -> str | None:
    if len(tool_calls) != 1:
        return None
    tool_name = tool_calls[0].get("function_name", "")
    rule = _RULES.get(tool_name)
    if rule and rule.canned_summary:
        return rule.canned_summary(tool_calls, tool_results)
    return None


def build_prompt_hints(available_tool_names: set[str]) -> str:
    hints: list[str] = []
    for name, rule in _RULES.items():
        if name in available_tool_names and rule.prompt_hint:
            hint = rule.prompt_hint().strip()
            if hint:
                hints.append(hint)
    return "\n\n".join(hints)


def _compact_inbox_list(content: str) -> str:
    try:
        data = json.loads(content)
        emails = data.get("emails")
        if not isinstance(emails, list):
            return content
        compact = [
            {
                "index": i + 1,
                "from": e.get("from", ""),
                "subject": e.get("subject", ""),
                "date": e.get("date", ""),
            }
            for i, e in enumerate(emails)
        ]
        return json.dumps(
            {"count": data.get("count", len(compact)), "emails": compact},
            ensure_ascii=False,
        )
    except (json.JSONDecodeError, TypeError):
        return content


def _inbox_canned_summary(_tool_calls: list[dict], tool_results: list[dict]) -> str | None:
    for tr in tool_results:
        if tr.get("tool_name") != "check_inbox":
            continue
        try:
            data = json.loads(tr.get("content", ""))
            if data.get("error"):
                return None
            count = int(data.get("count", 0))
            return (
                f"已加载最近 {count} 封邮件，详见上方列表。"
                "需要我帮您查看某封详情或处理待办吗？"
            )
        except (json.JSONDecodeError, TypeError, ValueError):
            return None
    return None


def _inbox_prompt_hint() -> str:
    return (
        "The UI renders check_inbox results as a table — never repeat the full email list in your reply.\n\n"
        "For 最近/最新邮件 requests use check_inbox with unread_only=false (default). "
        "Use unread_only=true only when the user explicitly asks for 未读邮件.\n\n"
        "Email walkthrough: when the user says 继续, 下一封, or 第N封 after viewing inbox, call read_inbox_email "
        "with the correct index (1=newest). Track which index you last showed and increment for 继续/下一封. "
        "Do not call check_inbox again during the same walkthrough."
    )


def _read_inbox_email_hint() -> str:
    return (
        "Use read_inbox_email to open a single message by index when the user asks to read or continue through mail."
    )


register_rule(
    "check_inbox",
    ToolPostprocessRule(
        compact_for_llm=_compact_inbox_list,
        canned_summary=_inbox_canned_summary,
        prompt_hint=_inbox_prompt_hint,
    ),
)
register_rule(
    "read_inbox_email",
    ToolPostprocessRule(prompt_hint=_read_inbox_email_hint),
)
