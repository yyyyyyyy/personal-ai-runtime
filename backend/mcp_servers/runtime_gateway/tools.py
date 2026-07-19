"""Tool implementations for the Runtime Gateway (HTTP @public / read surfaces)."""

from __future__ import annotations

import os
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass
from typing import Any
from urllib.parse import urlencode

from mcp_servers.runtime_gateway.http_client import request

_MAX_N_RESULTS = 20
_MAX_MEMORY_CONTENT = 4000
_MAX_TIMELINE = 50

# Core tools map to API endpoints marked **@public**.
CORE_TOOLS = frozenset({"recall", "store_memory"})
# Extended read surfaces — still HTTP-authenticated, but not the minimal SDK.
EXTENDED_TOOLS = frozenset({"list_pending_approvals", "recent_timeline"})
ALL_TOOLS = CORE_TOOLS | EXTENDED_TOOLS


@dataclass(frozen=True, slots=True)
class ToolOutput:
    text: str
    is_error: bool = False


def resolve_enabled_tools(raw: str | None = None) -> frozenset[str]:
    """Parse ``PAR_GATEWAY_TOOLS``.

    Values:
      - ``all`` (default): core + extended
      - ``core``: recall + store_memory only
      - comma list: explicit names (unknown names ignored)
    """
    text = (raw if raw is not None else os.environ.get("PAR_GATEWAY_TOOLS", "all")).strip().lower()
    if not text or text == "all":
        return ALL_TOOLS
    if text == "core":
        return CORE_TOOLS
    names = {part.strip() for part in text.split(",") if part.strip()}
    return frozenset(names & ALL_TOOLS) or CORE_TOOLS


def clamp_n(n_results: Any, *, default: int = 5, hard_max: int = _MAX_N_RESULTS) -> int:
    try:
        n = int(n_results)
    except (TypeError, ValueError):
        n = default
    return max(1, min(n, hard_max))


def memory_items(payload: Any) -> list[dict[str, Any]]:
    """Normalize memory search payloads (list or wrapped dict)."""
    if isinstance(payload, list):
        return [m for m in payload if isinstance(m, dict)]
    if isinstance(payload, dict):
        for key in ("items", "memories", "results"):
            value = payload.get(key)
            if isinstance(value, list):
                return [m for m in value if isinstance(m, dict)]
    return []


def tool_recall(query: str, n_results: int = 5) -> ToolOutput:
    """Recall what the user already knows about a topic."""
    query = (query or "").strip()
    if not query:
        return ToolOutput("query 不能为空", is_error=True)
    n = clamp_n(n_results)

    mem_qs = urlencode({"q": query, "n": n})
    know_qs = urlencode({"query": query, "n_results": n})

    with ThreadPoolExecutor(max_workers=2) as pool:
        fut_mem = pool.submit(request, "GET", f"/api/memory/memories/search?{mem_qs}")
        fut_know = pool.submit(request, "GET", f"/api/knowledge/search?{know_qs}")
        mem = fut_mem.result()
        know = fut_know.result()

    lines: list[str] = []
    errors = 0

    if not mem.ok:
        errors += 1
        lines.append(f"[memory search error: {mem.error}]")
    else:
        items = memory_items(mem.data)
        if items:
            lines.append("## 相关记忆")
            for i, m in enumerate(items, 1):
                content = str(m.get("content", ""))[:200]
                lines.append(f"{i}. {content}")

    if not know.ok:
        errors += 1
        lines.append(f"[knowledge search error: {know.error}]")
    elif isinstance(know.data, dict):
        docs = know.data.get("results") or []
        if docs:
            lines.append("\n## 相关文档")
            for i, d in enumerate(docs, 1):
                if not isinstance(d, dict):
                    continue
                meta = d.get("metadata") or {}
                fname = (
                    meta.get("source_file", "document")
                    if isinstance(meta, dict)
                    else "document"
                )
                snippet = (d.get("content") or "")[:200].replace("\n", " ")
                lines.append(f"{i}. [{fname}] {snippet}")

    if not lines:
        return ToolOutput("未找到相关记忆或文档")
    return ToolOutput("\n".join(lines), is_error=errors == 2)


def tool_store_memory(content: str, category: str = "fact") -> ToolOutput:
    """Store a durable fact about the user into long-term memory."""
    content = (content or "").strip()
    if not content:
        return ToolOutput("content 不能为空", is_error=True)
    if len(content) > _MAX_MEMORY_CONTENT:
        return ToolOutput(
            f"content 过长（最长 {_MAX_MEMORY_CONTENT} 字符）",
            is_error=True,
        )
    category = (category or "fact").strip() or "fact"
    if len(category) > 64 or any(c.isspace() for c in category):
        return ToolOutput("category 非法", is_error=True)

    result = request(
        "POST", "/api/memory/memories", {"content": content, "category": category}
    )
    if result.ok and isinstance(result.data, dict) and result.data.get("id"):
        return ToolOutput(f"已记住 (id={result.data['id']}): {content[:100]}")
    err = result.error or result.data
    return ToolOutput(f"存储失败: {err}", is_error=True)


def tool_list_pending_approvals(limit: int = 20) -> ToolOutput:
    """List pending capability approvals waiting for the user."""
    limit = clamp_n(limit, default=20, hard_max=50)
    qs = urlencode({"pending_only": "true", "enriched": "true", "limit": limit})
    result = request("GET", f"/api/approvals/?{qs}")
    if not result.ok:
        return ToolOutput(f"获取审批失败: {result.error}", is_error=True)

    rows = result.data if isinstance(result.data, list) else []
    if not rows:
        return ToolOutput("当前没有待处理审批")

    lines = [f"## 待处理审批 ({len(rows)})"]
    for i, row in enumerate(rows[:limit], 1):
        if not isinstance(row, dict):
            continue
        aid = row.get("id", "?")
        # Kernel projection uses ``action``; some enriched views may alias.
        cap = row.get("action") or row.get("capability_name") or row.get("capability") or "?"
        flow = row.get("flow_label") or row.get("flow_type") or ""
        reason = str(row.get("reason") or row.get("summary") or "")[:120]
        prefix = f"{i}. [{aid}] {cap}"
        if flow:
            prefix += f" · {flow}"
        if reason:
            prefix += f" — {reason}"
        lines.append(prefix)
    return ToolOutput("\n".join(lines))


def tool_recent_timeline(n_results: int = 15, event_type: str | None = None) -> ToolOutput:
    """Fetch recent human-readable timeline events."""
    n = clamp_n(n_results, default=15, hard_max=_MAX_TIMELINE)
    params: dict[str, Any] = {"page": 1, "page_size": n}
    if event_type and str(event_type).strip():
        params["event_type"] = str(event_type).strip()
    result = request("GET", f"/api/timeline/events?{urlencode(params)}")
    if not result.ok:
        return ToolOutput(f"获取时间线失败: {result.error}", is_error=True)
    if not isinstance(result.data, dict):
        return ToolOutput("时间线响应格式异常", is_error=True)

    items = result.data.get("items") or []
    if not items:
        return ToolOutput("最近没有时间线事件")

    lines = ["## 最近动态"]
    for i, item in enumerate(items, 1):
        if not isinstance(item, dict):
            continue
        ts = str(item.get("ts") or "")[:19]
        desc = item.get("description") or item.get("type") or "?"
        lines.append(f"{i}. {ts} {desc}")
    return ToolOutput("\n".join(lines))


# Re-export for monkeypatch convenience in tests.
_http = request
