"""Query Analyzer — 从用户消息中分析意图标签。

第一版仅规则匹配，不依赖 LLM，不依赖数据库，纯函数。
支持英文词边界匹配（\b），避免 "decode" 误命中 "code"。
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field

# ── 意图关键词映射 ────────────────────────────────────────────────────────

# Format: intent → {keyword: pattern}
# English keywords use \b word boundary matching.
# Chinese keywords use exact substring matching.
_INTENT_PATTERNS: dict[str, list[str]] = {
    "planning": [
        r"\bplan\b", r"\bschedule\b", r"\broadmap\b",
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
        r"\bbuild\b", r"\btest\b",
        "代码", "修复", "bug", "改", "写一个", "实现", "重构", "编译",
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

    第一版仅规则匹配。英文关键词使用 \b 词边界，中文使用子串匹配。
    未来可升级为 LLM-based 分析器。
    """

    def analyze(self, message: str) -> AnalysisResult:
        """分析用户消息，返回匹配的意图标签。"""
        if not message:
            return AnalysisResult()

        tags: set[str] = set()
        text_lower = message.lower()

        for intent, patterns in _INTENT_PATTERNS.items():
            for pat in patterns:
                try:
                    if re.search(pat, text_lower):
                        tags.add(intent)
                        break
                except re.error:
                    continue

        return AnalysisResult(tags=tags)
