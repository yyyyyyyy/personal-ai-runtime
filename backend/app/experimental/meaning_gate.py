"""Meaning Gate — presentation-layer guards for Identity / Meaning Boundary.

Chat responses MUST NOT frame proposed inferences as definitive identity.
See IDENTITY_RFC.md N2, §6 Q4.

Hybrid approach:
  1. Regex fast path — catches obvious destiny/outcome-backfill patterns
  2. Ollama semantic classifier — secondary check for flagged sentences
"""

from __future__ import annotations

import json
import logging
import re
from typing import Any

import httpx

from app.config import settings

logger = logging.getLogger(__name__)

# --- Regex layer: fast path for obvious destiny/outcome patterns ---

_DESTINY_PATTERNS: list[tuple[re.Pattern[str], str]] = [
    (re.compile(r"你就是这样的人"), "你呈现出一些相关倾向（系统推测，非定论）"),
    (re.compile(r"你一直是([\u4e00-\u9fff]{1,8})型"), r"系统注意到你可能有\1方面的重复模式（待你确认）"),
    (re.compile(r"你本来就是"), "从现有记录看，你可能（系统推测）"),
    (re.compile(r"天生适合"), "在某些条件下可能更适合"),
    (re.compile(r"你是([\u4e00-\u9fff]{1,24})"), r"系统推测你可能与\1相关（非身份认定）"),
    # --- Extended patterns (P0.3) ---
    (re.compile(r"你骨子里就是"), "系统发现你可能存在某种倾向（非定论）"),
    (re.compile(r"你的性格决定了"), "从行为模式看，你可能（系统推测）"),
    (re.compile(r"你永远不会改变"), "目前的数据显示（请注意这只反映过去模式）"),
    (re.compile(r"你这辈子都"), "你在过去一段时间内（系统推测）"),
    (re.compile(r"你注定"), "数据表明你可能更倾向于（非定论）"),
    (re.compile(r"你命里"), "从已有记录看，你或许（系统推测）"),
    (re.compile(r"从小就是"), "从记录来看，你表现出（系统推测）"),
    (re.compile(r"改不了"), "目前的数据尚未反映这一点（系统推测）"),
    (re.compile(r"江山易改"), "行为模式有时持续存在，但也可能变化"),
    (re.compile(r"你这类人"), "与你类似行为模式的用户中（系统推测）"),
    (re.compile(r"(本质上|根本)就是一个"), "从记录看，你似乎表现出（非身份认定）"),
    (re.compile(r"真正的你是"), "从证据来看，你可能（系统推测，非定论）"),
    (re.compile(r"你活成了"), "你的行为模式与（系统推测）"),
]

_OUTCOME_EPILOGUE = [
    re.compile(r"当年(的)?选择是正确的"),
    re.compile(r"证明了你(当时)?是对的"),
    re.compile(r"事实证明你"),
    re.compile(r"现在回头看"),
    re.compile(r"时间?最终?证明了"),
    re.compile(r"结局?印证了"),
    re.compile(r"这?再一次?说明你当初"),
]


class MeaningGateClassifier:
    """Ollama-based semantic classifier for destiny-framing detection.

    Used as a secondary defense when regex matches a sentence — Ollama confirms
    whether the flagged text is truly a destiny claim or a false positive.
    """

    _SYSTEM_PROMPT = (
        '你是一个文本分类器。你的唯一任务是判断给定句子是否将系统推断表述为对人的定论。\n'
        '定论包括：将系统推测表述为事实（如"你就是……"）、将过去行为固化为性格（如"你骨子里"）、\n'
        '用后期结果重写前期选择的正当性（如"事实证明你当年是对的"）。\n'
        '请仅回答 JSON: {"is_destiny": true/false, "reason": "一句话理由"}'
    )

    def __init__(self) -> None:
        self._ollama_url = getattr(settings, "ollama_base_url", None) or "http://localhost:11434/v1"
        self._enabled = bool(self._ollama_url)

    async def classify(self, sentence: str) -> dict[str, Any]:
        """Classify a single sentence. Returns {"is_destiny": bool, "reason": str}."""
        if not self._enabled or not sentence.strip():
            return {"is_destiny": False, "reason": "classifier disabled"}

        try:
            async with httpx.AsyncClient(timeout=30.0) as client:
                resp = await client.post(
                    f"{self._ollama_url}/chat/completions",
                    json={
                        "model": getattr(settings, "ollama_model", "qwen2.5:3b"),
                        "messages": [
                            {"role": "system", "content": self._SYSTEM_PROMPT},
                            {"role": "user", "content": sentence},
                        ],
                        "temperature": 0.0,
                        "max_tokens": 80,
                    },
                )
                if resp.status_code != 200:
                    logger.warning("MeaningGateClassifier Ollama error: %s %s", resp.status_code, resp.text[:200])
                    return {"is_destiny": False, "reason": f"ollama_error_{resp.status_code}"}

                content = resp.json()["choices"][0]["message"]["content"].strip()
                return self._parse_response(content)
        except Exception as exc:
            logger.warning("MeaningGateClassifier failed: %s", exc)
            return {"is_destiny": False, "reason": str(exc)[:100]}

    @staticmethod
    def _parse_response(content: str) -> dict[str, Any]:
        try:
            clean = content.strip()
            if clean.startswith("```"):
                clean = clean.split("\n", 1)[-1].rsplit("\n", 1)[0]
            parsed = json.loads(clean)
            if isinstance(parsed, dict):
                return parsed
            if isinstance(parsed, bool):
                return {"is_destiny": parsed, "reason": "json bool"}
            return {"is_destiny": False, "reason": "json non-dict"}
        except (json.JSONDecodeError, KeyError, IndexError):
            lower = content.lower()
            if "true" in lower:
                return {"is_destiny": True, "reason": "heuristic match"}
            return {"is_destiny": False, "reason": "heuristic fallback"}


_classifier: MeaningGateClassifier | None = None


def _get_classifier() -> MeaningGateClassifier:
    global _classifier
    if _classifier is None:
        _classifier = MeaningGateClassifier()
    return _classifier


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


async def gate_assistant_text_async(text: str) -> tuple[str, list[str]]:
    """Async variant that uses Ollama classifier for secondary confirmation."""
    if not text or not text.strip():
        return text, []

    warnings: list[str] = []
    out = text

    classifier = _get_classifier()

    for pat, repl in _DESTINY_PATTERNS:
        if pat.search(out):
            warnings.append(f"meaning_gate: destiny framing detected ({pat.pattern})")
            out = pat.sub(repl, out)

    for pat in _OUTCOME_EPILOGUE:
        if pat.search(out):
            warnings.append(f"meaning_gate: outcome epilogue detected ({pat.pattern})")
            out = pat.sub("（该表述涉及结果回填，已改写为开放叙述）", out)

    # If regex flagged anything, run Ollama as secondary defense
    if warnings:
        result = await classifier.classify(text)
        if result.get("is_destiny"):
            warnings.append(f"meaning_gate: Ollama confirmed destiny framing: {result.get('reason', '')}")
        else:
            warnings.append(f"meaning_gate: Ollama cleared — regex flag may be false positive: {result.get('reason', '')}")

    return out, warnings


def gate_assistant_text(text: str) -> tuple[str, list[str]]:
    """Sanitize assistant text synchronously (regex-only fast path).

    For the full hybrid path with Ollama confirmation, use gate_assistant_text_async.
    """
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
