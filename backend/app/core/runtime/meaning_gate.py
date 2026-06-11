"""Meaning Gate — presentation-layer guards for Identity / Meaning Boundary.

Chat responses MUST NOT frame proposed inferences as definitive identity.
See IDENTITY_RFC.md N2, §6 Q4.
"""

from __future__ import annotations

import re

# Destiny framing patterns (mirror identity_lint N2 / I-F3).
_DESTINY_PATTERNS: list[tuple[re.Pattern[str], str]] = [
    (re.compile(r"你就是这样的人"), "你呈现出一些相关倾向（系统推测，非定论）"),
    (re.compile(r"你一直是([\u4e00-\u9fff]{1,8})型"), r"系统注意到你可能有\1方面的重复模式（待你确认）"),
    (re.compile(r"你本来就是"), "从现有记录看，你可能（系统推测）"),
    (re.compile(r"天生适合"), "在某些条件下可能更适合"),
    (re.compile(r"你是([\u4e00-\u9fff]{1,24})"), r"系统推测你可能与\1相关（非身份认定）"),
]

_OUTCOME_EPILOGUE = [
    re.compile(r"当年(的)?选择是正确的"),
    re.compile(r"证明了你(当时)?是对的"),
    re.compile(r"事实证明你"),
]


def _ends_sentence(text: str) -> bool:
    stripped = text.rstrip()
    if not stripped:
        return False
    return stripped[-1] in "。！？!?\n"


def gate_stream_delta(
    accumulated: str, delta: str
) -> tuple[str, str, list[str]]:
    """Gate streaming text at sentence boundaries; return (new_accumulated, safe_delta, warnings)."""
    new_accumulated = accumulated + delta
    if not _ends_sentence(new_accumulated):
        return new_accumulated, delta, []

    gated, warnings = gate_assistant_text(new_accumulated)
    if gated == new_accumulated:
        return new_accumulated, delta, warnings

    safe_delta = gated[len(accumulated):] if len(gated) >= len(accumulated) else gated
    return gated, safe_delta, warnings


def gate_assistant_text(text: str) -> tuple[str, list[str]]:
    """Sanitize assistant text; return (possibly modified text, warnings)."""
    if not text or not text.strip():
        return text, []

    warnings: list[str] = []
    out = text

    for pat, repl in _DESTINY_PATTERNS:
        if pat.search(out):
            warnings.append(f"meaning_gate: softened destiny framing ({pat.pattern})")
            out = pat.sub(repl, out)

    for pat in _OUTCOME_EPILOGUE:
        if pat.search(out):
            warnings.append(f"meaning_gate: blocked outcome epilogue ({pat.pattern})")
            out = pat.sub("（该表述涉及结果回填，已改写为开放叙述）", out)

    return out, warnings
