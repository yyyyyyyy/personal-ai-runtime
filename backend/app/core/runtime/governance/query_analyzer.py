"""Query Analyzer — 从用户消息中分析意图标签。

第一版仅规则匹配，不依赖 LLM，不依赖数据库，纯函数。
"""

from __future__ import annotations

from dataclasses import dataclass, field

# ── 意图关键词映射 ────────────────────────────────────────────────────────

_INTENT_KEYWORDS: dict[str, set[str]] = {
    "planning": {"规划", "计划", "安排", "下周", "本周", "本月", "接下来", "要做",
                 "plan", "schedule", "roadmap", "安排任务", "新目标"},
    "review":   {"复盘", "总结", "回顾", "review", "reflect", "审视", "检查进度",
                 "本周总结", "日报", "周报", "月报"},
    "coding":   {"代码", "修复", "bug", "改", "写一个", "实现", "重构", "编译",
                 "code", "fix", "implement", "refactor", "测试", "build"},
    "memory":   {"记得", "回忆", "之前说过", "上次", "我讲过", "记忆", "记住",
                 "learn", "remember"},
    "knowledge": {"知识库", "文档", "找一下", "有没有关于", "查", "资料",
                  "knowledge", "search doc"},
    "mail":     {"邮件", "收件箱", "inbox", "email", "发信", "回复邮件", "查邮件",
                 "gmail", "信"},
    "goals":    {"目标", "进度", "goal", "goals", "okr", "里程碑", "完成度",
                 "人生目标", "年度计划"},
    "calendar": {"日历", "日程", "会议", "约会", "calendar", "schedule",
                 "今天安排", "明天有什么", "议程", "appointment"},
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

    第一版仅规则匹配。未来可升级为 LLM-based 分析器。
    """

    def analyze(self, message: str) -> AnalysisResult:
        """分析用户消息，返回匹配的意图标签。"""
        if not message:
            return AnalysisResult()

        tags: set[str] = set()
        text = message.lower()

        for intent, keywords in _INTENT_KEYWORDS.items():
            for kw in keywords:
                if kw.lower() in text or kw in message:
                    tags.add(intent)
                    break

        return AnalysisResult(tags=tags)
