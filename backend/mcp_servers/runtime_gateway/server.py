"""Runtime Gateway MCP Server — exposes Personal AI Runtime's @public SDK
surface to external agents (Cursor, Claude Code, any MCP-compatible client).

This is the Phase 3.2 dogfood: by pointing Cursor at this MCP server, the
author's IDE agent gains access to long-term memory + knowledge recall,
proving (or disproving) the "runtime as infrastructure" thesis.

Tools exposed:
  - recall: unified semantic search across memories + knowledge documents
  - store_memory: persist a fact into long-term memory (event-sourced)

The server talks to the local backend over HTTP (@public memory/knowledge endpoints).
It does NOT import the runtime directly —
that's the whole point: external agents should depend on the HTTP contract,
not Python internals.

Usage from Cursor / Claude Desktop config:
  {
    "mcpServers": {
      "personal-ai-runtime": {
        "command": "python3",
        "args": ["-m", "mcp_servers.runtime_gateway.server"],
        "env": {
          "PAR_BASE_URL": "http://localhost:8000",
          "PAR_AUTH_TOKEN": "<your AUTH_TOKEN>"
        }
      }
    }
  }
"""

from __future__ import annotations

import json
import os
import sys
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

BASE_URL = os.environ.get("PAR_BASE_URL", "http://localhost:8000").rstrip("/")
AUTH_TOKEN = os.environ.get("PAR_AUTH_TOKEN", "")


def _http(method: str, path: str, body: dict | None = None) -> dict:
    url = f"{BASE_URL}{path}"
    data = json.dumps(body).encode() if body else None
    headers = {"Content-Type": "application/json"}
    if AUTH_TOKEN:
        headers["Authorization"] = f"Bearer {AUTH_TOKEN}"
    req = Request(url, data=data, headers=headers, method=method)
    try:
        with urlopen(req, timeout=15) as resp:
            return json.loads(resp.read().decode())
    except (HTTPError, URLError) as e:
        return {"error": str(e)}


# ── Tool implementations ────────────────────────────────────────────────────

def tool_recall(query: str, n_results: int = 5) -> str:
    """Recall what the user already knows about a topic.

    Searches both personal memories (auto-extracted facts, preferences,
    history) AND knowledge documents (uploaded PDFs/notes) in one pass.
    Use this before answering questions to leverage the user's context.
    """
    # Try unified memory search first
    mem = _http("GET", f"/api/memory/memories/search?q={_enc(query)}&n={n_results}")
    # Then knowledge search
    know = _http("POST", "/api/knowledge/search", {"query": query, "n_results": n_results})

    lines = []
    mem_items = mem if isinstance(mem, list) else []
    if isinstance(mem, dict) and "error" in mem:
        lines.append(f"[memory search error: {mem['error']}]")
    elif mem_items:
        lines.append("## 相关记忆")
        for i, m in enumerate(mem_items, 1):
            content = m.get("content", "")[:200]
            lines.append(f"{i}. {content}")

    if isinstance(know, dict) and "results" in know:
        docs = know["results"]
        if docs:
            lines.append("\n## 相关文档")
            for i, d in enumerate(docs, 1):
                meta = d.get("metadata") or {}
                fname = meta.get("source_file", "document")
                snippet = (d.get("content") or "")[:200].replace("\n", " ")
                lines.append(f"{i}. [{fname}] {snippet}")
    elif isinstance(know, dict) and "error" in know:
        lines.append(f"[knowledge search error: {know['error']}]")

    return "\n".join(lines) if lines else "未找到相关记忆或文档"


def tool_store_memory(content: str, category: str = "fact") -> str:
    """Store a durable fact about the user into long-term memory.

    The memory is event-sourced (survives rebuilds), searchable later via
    recall, and will decay over time unless the user confirms it. Use this
    when the user shares a preference, fact, or decision worth remembering.
    """
    result = _http("POST", "/api/memory/memories", {"content": content, "category": category})
    if isinstance(result, dict) and result.get("id"):
        return f"已记住 (id={result['id']}): {content[:100]}"
    return f"存储失败: {result}"


def _enc(s: str) -> str:
    import urllib.parse
    return urllib.parse.quote(s)


# ── stdio MCP protocol (minimal JSON-RPC over stdin/stdout) ─────────────────

TOOLS = [
    {
        "name": "recall",
        "description": "Recall what the user already knows. Searches memories + knowledge documents.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "query": {"type": "string", "description": "What to recall about"},
                "n_results": {"type": "integer", "description": "Max results per source", "default": 5},
            },
            "required": ["query"],
        },
    },
    {
        "name": "store_memory",
        "description": "Store a durable fact about the user into long-term memory.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "content": {"type": "string", "description": "The fact/preference to remember"},
                "category": {"type": "string", "description": "Memory category", "default": "fact"},
            },
            "required": ["content"],
        },
    },
]


def _handle(request: dict) -> dict:
    method = request.get("method", "")
    req_id = request.get("id")

    if method == "initialize":
        return {"jsonrpc": "2.0", "id": req_id, "result": {
            "protocolVersion": "2024-11-05",
            "capabilities": {"tools": {}},
            "serverInfo": {"name": "personal-ai-runtime", "version": "0.1.0"},
        }}

    if method == "tools/list":
        return {"jsonrpc": "2.0", "id": req_id, "result": {"tools": TOOLS}}

    if method == "tools/call":
        params = request.get("params", {})
        name = params.get("name", "")
        args = params.get("arguments", {}) or {}
        if name == "recall":
            output = tool_recall(args.get("query", ""), args.get("n_results", 5))
        elif name == "store_memory":
            output = tool_store_memory(args.get("content", ""), args.get("category", "fact"))
        else:
            output = f"Unknown tool: {name}"
        return {"jsonrpc": "2.0", "id": req_id, "result": {
            "content": [{"type": "text", "text": output}],
        }}

    if method == "notifications/initialized":
        return {}  # notification, no response

    return {"jsonrpc": "2.0", "id": req_id, "error": {
        "code": -32601, "message": f"Method not found: {method}",
    }}


def main() -> None:
    for line in sys.stdin:
        line = line.strip()
        if not line:
            continue
        try:
            request = json.loads(line)
        except json.JSONDecodeError:
            continue
        response = _handle(request)
        if response:
            sys.stdout.write(json.dumps(response) + "\n")
            sys.stdout.flush()


if __name__ == "__main__":
    main()
