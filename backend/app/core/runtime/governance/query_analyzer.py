"""Query Analyzer — 从用户消息中分析意图标签。

第一版仅规则匹配，不依赖 LLM，不依赖数据库，纯函数。
支持英文词边界匹配（\\b），避免 "decode" 误命中 "code"。
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field

# ── 意图关键词映射 ────────────────────────────────────────────────────────

# Format: intent → patterns (English use \\b; Chinese use substring).
# ``schedule`` is calendar-only to avoid also tagging planning.
_INTENT_PATTERNS: dict[str, list[str]] = {
    "planning": [
        r"\bplan\b", r"\broadmap\b",
        "规划", "计划", "安排", "下周", "本周", "本月", "接下来", "要做",
        "安排任务", "新目标",
    ],
    "review": [
        r"\breview\b", r"\breflect\b",
        "复盘", "总结", "回顾", "审视", "检查进度",
        "本周总结", "日报", "周报", "月报",
    ],
    "coding": [
        r"\bcode\b", r"\bfix\b", r"\bimplement\b", r"\brefactor\b",
        r"\bbuild\b", r"\bdebug\b", r"\bpatch\b", r"\bpytest\b",
        r"\bpython\b", r"\btypescript\b", r"\btraceback\b",
        "代码", "修复", "bug", "写一个", "实现", "重构", "编译",
        "改代码", "改文件", "改函数", "修改代码", "修改文件",
        "写代码", "写个函数", "调试", "报错", "优化代码",
        "这个函数", "这个文件", "这个类",
    ],
    "memory": [
        r"\blearn\b", r"\bremember\b",
        "记得", "回忆", "之前说过", "上次", "我讲过", "记忆", "记住",
    ],
    "knowledge": [
        r"\bknowledge\b", r"\bsearch doc\b",
        "知识库", "文档", "找一下", "有没有关于", "查", "资料",
    ],
    "mail": [
        r"\binbox\b", r"\bemail\b", r"\bgmail\b",
        "邮件", "收件箱", "发信", "回复邮件", "查邮件",
    ],
    "goals": [
        r"\bgoal\b", r"\bgoals\b", r"\bokr\b",
        "目标", "进度", "里程碑", "完成度", "人生目标", "年度计划",
    ],
    "calendar": [
        r"\bcalendar\b", r"\bschedule\b", r"\bmeeting\b", r"\bappointment\b",
        "日历", "日程", "会议", "约会", "今天安排", "明天有什么", "议程",
    ],
}


def _compile_patterns(
    raw: dict[str, list[str]],
) -> dict[str, list[re.Pattern[str]]]:
    compiled: dict[str, list[re.Pattern[str]]] = {}
    for intent, patterns in raw.items():
        compiled[intent] = []
        for pat in patterns:
            try:
                compiled[intent].append(re.compile(pat))
            except re.error:
                continue
    return compiled


_COMPILED_INTENT_PATTERNS = _compile_patterns(_INTENT_PATTERNS)


@dataclass
class AnalysisResult:
    """Query Analysis 结果。"""
    tags: set[str] = field(default_factory=set)

    @property
    def has_planning(self) -> bool:
        return "planning" in self.tags

    @property
    def has_review(self) -> bool:
        return "review" in self.tags

    @property
    def has_coding(self) -> bool:
        return "coding" in self.tags


class QueryAnalyzer:
    """从用户消息分析意图标签。

    第一版仅规则匹配。英文关键词使用 \\b 词边界，中文使用子串匹配。
    未来可升级为 LLM-based 分析器。
    """

    def __init__(
        self,
        patterns: dict[str, list[re.Pattern[str]]] | None = None,
    ) -> None:
        self._patterns = patterns or _COMPILED_INTENT_PATTERNS

    def analyze(self, message: str) -> AnalysisResult:
        """分析用户消息，返回匹配的意图标签。"""
        if not message:
            return AnalysisResult()

        tags: set[str] = set()
        text_lower = message.lower()

        for intent, patterns in self._patterns.items():
            for pat in patterns:
                if pat.search(text_lower):
                    tags.add(intent)
                    break
        return AnalysisResult(tags=tags)


# Shared singleton for hot paths (PromptCompiler / Artifact).
_default_analyzer = QueryAnalyzer()


def get_default_analyzer() -> QueryAnalyzer:
    """Public accessor for the process-wide QueryAnalyzer singleton."""
    return _default_analyzer
