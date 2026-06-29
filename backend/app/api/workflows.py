"""Workflow API — visual workflow CRUD, executable plan export, and scene templates.

Workflows are visual representations of Trigger → Action chains that compile
into executable_plan JSON understood by BackgroundWorker/TaskEngine.
Scene templates are pre-built workflows users can instantiate with one click.
"""

import json
import uuid
from datetime import UTC, datetime

from fastapi import APIRouter, HTTPException

from app.store.database import db

router = APIRouter(prefix="/api/workflows", tags=["workflows"])

WORKFLOW_CATEGORY = "workflows"


def _load_workflows() -> dict[str, dict]:
    try:
        with db.get_db() as conn:
            row = conn.execute(
                "SELECT data_json FROM app_settings WHERE category = ?",
                (WORKFLOW_CATEGORY,),
            ).fetchone()
        if row:
            return json.loads(row["data_json"])
    except Exception:
        pass
    return {}


def _save_workflows(data: dict[str, dict]) -> None:
    now = datetime.now(UTC).isoformat()
    with db.get_db() as conn:
        conn.execute(
            """INSERT INTO app_settings (category, data_json, updated_at)
               VALUES (?, ?, ?)
               ON CONFLICT(category) DO UPDATE SET
                 data_json = excluded.data_json,
                 updated_at = excluded.updated_at""",
            (WORKFLOW_CATEGORY, json.dumps(data, ensure_ascii=False), now),
        )


@router.get("")
async def list_workflows():
    wf = _load_workflows()
    items = sorted(wf.values(), key=lambda w: w.get("updated_at", ""), reverse=True)
    return {"workflows": items, "total": len(items)}


@router.post("")
async def create_workflow(body: dict):
    wf_id = str(uuid.uuid4())
    now = datetime.now(UTC).isoformat()

    wf_data = {
        "id": wf_id,
        "name": body.get("name", "未命名工作流"),
        "description": body.get("description", ""),
        "nodes": body.get("nodes", []),
        "edges": body.get("edges", []),
        "enabled": body.get("enabled", False),
        "created_at": now,
        "updated_at": now,
    }
    all_wf = _load_workflows()
    all_wf[wf_id] = wf_data
    _save_workflows(all_wf)
    return wf_data


@router.put("/{workflow_id}")
async def update_workflow(workflow_id: str, body: dict):
    all_wf = _load_workflows()
    if workflow_id not in all_wf:
        raise HTTPException(status_code=404, detail="工作流不存在")

    wf = all_wf[workflow_id]
    for key in ("name", "description", "nodes", "edges", "enabled"):
        if key in body:
            wf[key] = body[key]
    wf["updated_at"] = datetime.now(UTC).isoformat()
    all_wf[workflow_id] = wf
    _save_workflows(all_wf)
    return wf


@router.delete("/{workflow_id}")
async def delete_workflow(workflow_id: str):
    all_wf = _load_workflows()
    if workflow_id not in all_wf:
        raise HTTPException(status_code=404, detail="工作流不存在")
    del all_wf[workflow_id]
    _save_workflows(all_wf)
    return {"ok": True}


@router.get("/{workflow_id}/export")
async def export_executable_plan(workflow_id: str):
    """Compile workflow nodes/edges into executable_plan JSON for BackgroundWorker."""
    all_wf = _load_workflows()
    if workflow_id not in all_wf:
        raise HTTPException(status_code=404, detail="工作流不存在")

    wf = all_wf[workflow_id]
    nodes = wf.get("nodes", [])
    edges = wf.get("edges", [])

    # Build adjacency: node_id → children
    children: dict[str, list[str]] = {n["id"]: [] for n in nodes}
    for e in edges:
        src = e.get("source", "")
        tgt = e.get("target", "")
        if src in children:
            children[src].append(tgt)

    # Topological sort (simple DFS)
    visited = set()
    order: list[str] = []

    def dfs(nid: str):
        if nid in visited:
            return
        visited.add(nid)
        for child in children.get(nid, []):
            dfs(child)
        order.append(nid)

    # Start from trigger nodes
    triggers = [n for n in nodes if n.get("type") in ("trigger", "schedule")]
    for t in triggers:
        dfs(t["id"])

    # Add remaining
    for n in nodes:
        if n["id"] not in visited:
            dfs(n["id"])

    order.reverse()

    # Build steps
    steps = []
    for nid in order:
        node = next((n for n in nodes if n["id"] == nid), None)
        if not node:
            continue
        node_type = node.get("type", "")
        data = node.get("data", {})

        if node_type in ("trigger", "schedule"):
            steps.append({
                "tool": "null",
                "params": {},
                "reason": f"Trigger: {node.get('label', '')}",
                "trigger": {
                    "type": node_type,
                    "schedule": data.get("schedule", ""),
                    "event": data.get("event", ""),
                },
            })
        elif node_type == "agent":
            steps.append({
                "tool": data.get("tool", "chat"),
                "params": data.get("params", {}),
                "reason": node.get("label", ""),
                "requires_approval": data.get("requires_approval", False),
            })
        elif node_type == "action":
            steps.append({
                "tool": data.get("tool", "read_file"),
                "params": data.get("params", {}),
                "reason": node.get("label", ""),
                "requires_approval": data.get("requires_approval", False),
            })
        elif node_type == "notification":
            steps.append({
                "tool": "send_notification",
                "params": {
                    "title": data.get("title", ""),
                    "content": data.get("content", ""),
                },
                "reason": node.get("label", ""),
            })

    plan = {
        "goal": wf.get("name", ""),
        "steps": steps,
        "estimated_steps": len(steps),
        "workflow_id": workflow_id,
        "workflow_name": wf.get("name", ""),
    }

    return {"plan": plan, "workflow": wf}


# ── Node palette for frontend ──────────────────────────────────────────────

NODE_PALETTE = [
    {
        "type": "schedule",
        "label": "定时触发",
        "icon": "clock",
        "color": "#10b981",
        "description": "按 cron 表达式定时触发",
        "defaults": {"schedule": "0 8 * * *"},
    },
    {
        "type": "trigger",
        "label": "事件触发",
        "icon": "zap",
        "color": "#f59e0b",
        "description": "当特定事件发生时触发",
        "defaults": {"event": "inbox_email"},
    },
    {
        "type": "agent",
        "label": "AI 对话",
        "icon": "message-square",
        "color": "#6366f1",
        "description": "让 AI 处理或回答问题",
        "defaults": {"prompt": "请帮我处理"},
    },
    {
        "type": "action",
        "label": "工具调用",
        "icon": "wrench",
        "color": "#06b6d4",
        "description": "调用具体工具",
        "defaults": {"tool": "web_search", "params": {}},
    },
    {
        "type": "notification",
        "label": "发送通知",
        "icon": "bell",
        "color": "#f97316",
        "description": "通过通知通道发送消息",
        "defaults": {"title": "通知", "content": ""},
    },
]


@router.get("/_palette")
async def node_palette():
    return {"nodes": NODE_PALETTE}


# --- Scene Templates (Phase 2) ---

SCENE_TEMPLATES: list[dict] = [
    {
        "id": "template-inbox",
        "name": "管理邮件",
        "icon": "📬",
        "description": "定时轮询收件箱，自动分类重要邮件并通知你",
        "category": "productivity",
        "nodes": [
            {"id":"n1","type":"schedule","label":"每 15 分钟","data":{"cron":"minute=*/15"}},
            {"id":"n2","type":"action","label":"检查收件箱","data":{"tool":"check_inbox"}},
            {"id":"n3","type":"agent","label":"AI 分类","data":{"prompt":"根据内容将邮件分类为重要、普通、垃圾"}},
            {"id":"n4","type":"notification","label":"通知我","data":{"title":"新邮件摘要","content":"{summary}"}},
            {"id":"e1","source":"n1","target":"n2"},
            {"id":"e2","source":"n2","target":"n3"},
            {"id":"e3","source":"n3","target":"n4"},
        ],
    },
    {
        "id": "template-goals",
        "name": "追踪目标",
        "icon": "🎯",
        "description": "每日检查目标进度，停滞时自动提醒你",
        "category": "productivity",
        "nodes": [
            {"id":"n1","type":"schedule","label":"每天 9:00","data":{"cron":"hour=9,minute=0"}},
            {"id":"n2","type":"trigger","label":"检查停滞","data":{"event_type":"trigger_evaluation"}},
            {"id":"n3","type":"notification","label":"目标提醒","data":{"title":"目标进度提醒","content":"以下目标本周无进展：{stalled_goals}"}},
            {"id":"e1","source":"n1","target":"n2"},
            {"id":"e2","source":"n2","target":"n3"},
        ],
    },
    {
        "id": "template-daily",
        "name": "自动化日报",
        "icon": "📊",
        "description": "每天早晨生成昨日活动摘要并通知你",
        "category": "productivity",
        "nodes": [
            {"id":"n1","type":"schedule","label":"每天 7:30","data":{"cron":"hour=7,minute=30"}},
            {"id":"n2","type":"agent","label":"生成日报","data":{"prompt":"总结过去24小时的对话、目标和邮件活动，生成一份简洁日报"}},
            {"id":"n3","type":"notification","label":"推送日报","data":{"title":"今日日报","content":"{daily_summary}"}},
            {"id":"e1","source":"n1","target":"n2"},
            {"id":"e2","source":"n2","target":"n3"},
        ],
    },
    {
        "id": "template-memory",
        "name": "建立记忆",
        "icon": "🧠",
        "description": "定期从对话中提取关键信息，更新用户画像",
        "category": "cognition",
        "nodes": [
            {"id":"n1","type":"schedule","label":"每天 21:30","data":{"cron":"hour=21,minute=30"}},
            {"id":"n2","type":"trigger","label":"记忆反思","data":{"event_type":"belief_reflection"}},
            {"id":"n3","type":"agent","label":"更新画像","data":{"prompt":"根据最近对话更新用户偏好和习惯"}},
            {"id":"e1","source":"n1","target":"n2"},
            {"id":"e2","source":"n2","target":"n3"},
        ],
    },
]

@router.get("/templates")
async def list_templates():
    """List scene templates available for one-click instantiation."""
    return {"templates": SCENE_TEMPLATES}

@router.post("/from-template/{template_id}")
async def create_from_template(template_id: str):
    """Instantiate a workflow from a scene template."""
    template = next((t for t in SCENE_TEMPLATES if t["id"] == template_id), None)
    if not template:
        raise HTTPException(status_code=404, detail="Template not found")
    wf_id = str(uuid.uuid4())
    now = datetime.now(UTC).isoformat()
    wf_data = {
        "id": wf_id, "name": template["name"],
        "description": template.get("description", ""),
        "nodes": template["nodes"],
        "edges": template.get("edges", []),
        "enabled": False, "created_at": now, "updated_at": now,
    }
    all_wf = _load_workflows()
    all_wf[wf_id] = wf_data
    _save_workflows(all_wf)
    return {"id": wf_id, "name": template["name"], "status": "created"}
