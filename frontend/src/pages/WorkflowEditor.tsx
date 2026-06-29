import { useState, useCallback, useRef, useEffect } from "react";
import { useNavigate, useParams } from "react-router-dom";
import { API_BASE, request } from "../api/core";
import {
  Clock, Zap, MessageSquare, Wrench, Bell, Play, Save,
  Trash2, ArrowLeft, Plus, Download, Upload, Workflow,
} from "lucide-react";

interface FlowNode {
  id: string;
  type: string;
  label: string;
  x: number;
  y: number;
  data: Record<string, unknown>;
}

interface FlowEdge {
  id: string;
  source: string;
  target: string;
}

interface WorkflowData {
  id: string;
  name: string;
  description: string;
  nodes: FlowNode[];
  edges: FlowEdge[];
  enabled: boolean;
  created_at: string;
  updated_at: string;
}

interface PaletteItem {
  type: string;
  label: string;
  description: string;
  icon: string;
  color: string;
  defaults: Record<string, unknown>;
}

const ICON_MAP: Record<string, React.ReactNode> = {
  clock: <Clock size={14} />,
  zap: <Zap size={14} />,
  "message-square": <MessageSquare size={14} />,
  wrench: <Wrench size={14} />,
  bell: <Bell size={14} />,
};

function generateId() {
  return `node_${Date.now()}_${Math.random().toString(36).slice(2, 8)}`;
}

export default function WorkflowEditorPage() {
  const { workflowId } = useParams<{ workflowId?: string }>();
  const navigate = useNavigate();
  const canvasRef = useRef<HTMLDivElement>(null);

  const [name, setName] = useState("");
  const [description, setDescription] = useState("");
  const [nodes, setNodes] = useState<FlowNode[]>([]);
  const [edges, setEdges] = useState<FlowEdge[]>([]);
  const [palette, setPalette] = useState<PaletteItem[]>([]);
  const [selectedNode, setSelectedNode] = useState<string | null>(null);
  const [connecting, setConnecting] = useState<string | null>(null);
  const [saving, setSaving] = useState(false);
  const [loading, setLoading] = useState(true);
  const [message, setMessage] = useState("");

  // Load palette and existing workflow
  useEffect(() => {
    request<{ nodes: PaletteItem[] }>(`${API_BASE}/workflows/_palette`)
      .then((d) => setPalette(d.nodes))
      .catch(() => {});

    if (workflowId) {
      request<{ workflows: WorkflowData[] }>(`${API_BASE}/workflows`)
        .then((d) => {
          const wf = d.workflows.find((w) => w.id === workflowId);
          if (wf) {
            setName(wf.name);
            setDescription(wf.description || "");
            setNodes(wf.nodes);
            setEdges(wf.edges);
          }
        })
        .finally(() => setLoading(false));
    } else {
      setLoading(false);
    }
  }, [workflowId]);

  const addNode = useCallback((type: string, x: number, y: number) => {
    const paletteItem = palette.find((p) => p.type === type);
    const newNode: FlowNode = {
      id: generateId(),
      type,
      label: paletteItem?.label || type,
      x, y,
      data: { ...(paletteItem?.defaults || {}) },
    };
    setNodes((prev) => [...prev, newNode]);
    setSelectedNode(newNode.id);
  }, [palette]);

  const handleCanvasClick = useCallback((e: React.MouseEvent) => {
    if (!canvasRef.current) return;
    const rect = canvasRef.current.getBoundingClientRect();
    const x = e.clientX - rect.left;
    const y = e.clientY - rect.top;
    // Only add if clicking empty canvas (not on a node)
    if ((e.target as HTMLElement).closest("[data-node]")) return;
    setSelectedNode(null);
    setConnecting(null);
  }, []);

  const handleDrop = useCallback((e: React.DragEvent) => {
    e.preventDefault();
    const type = e.dataTransfer.getData("nodeType");
    if (!type || !canvasRef.current) return;
    const rect = canvasRef.current.getBoundingClientRect();
    const x = e.clientX - rect.left - 60;
    const y = e.clientY - rect.top - 20;
    addNode(type, x, y);
  }, [addNode]);

  const moveNode = useCallback((id: string, dx: number, dy: number) => {
    setNodes((prev) => prev.map((n) =>
      n.id === id ? { ...n, x: n.x + dx, y: n.y + dy } : n
    ));
  }, []);

  const deleteNode = useCallback((id: string) => {
    setNodes((prev) => prev.filter((n) => n.id !== id));
    setEdges((prev) => prev.filter((e) => e.source !== id && e.target !== id));
    setSelectedNode(null);
  }, []);

  const startConnect = useCallback((nodeId: string) => {
    setConnecting(nodeId);
    setSelectedNode(nodeId);
  }, []);

  const finishConnect = useCallback((targetId: string) => {
    if (connecting && connecting !== targetId) {
      const exists = edges.some(
        (e) => e.source === connecting && e.target === targetId
      );
      if (!exists) {
        setEdges((prev) => [...prev, {
          id: `edge_${connecting}_${targetId}`,
          source: connecting,
          target: targetId,
        }]);
      }
    }
    setConnecting(null);
  }, [connecting, edges]);

  const updateNodeData = useCallback((id: string, key: string, value: string) => {
    setNodes((prev) => prev.map((n) =>
      n.id === id ? { ...n, data: { ...n.data, [key]: value } } : n
    ));
  }, []);

  const save = useCallback(async () => {
    setSaving(true);
    setMessage("");
    try {
      const body = { name, description, nodes, edges, enabled: false };
      if (workflowId) {
        await request(`${API_BASE}/workflows/${workflowId}`, {
          method: "PUT", body: JSON.stringify(body),
        });
      } else {
        const result = await request<WorkflowData>(`${API_BASE}/workflows`, {
          method: "POST", body: JSON.stringify(body),
        });
        navigate(`/workflows/${result.id}`, { replace: true });
      }
      setMessage("已保存");
      setTimeout(() => setMessage(""), 2000);
    } catch {
      setMessage("保存失败");
    } finally {
      setSaving(false);
    }
  }, [name, description, nodes, edges, workflowId, navigate]);

  const handleDelete = useCallback(async () => {
    if (!workflowId) return;
    if (!confirm("确定删除此工作流？")) return;
    await request(`${API_BASE}/workflows/${workflowId}`, { method: "DELETE" });
    navigate("/workflows");
  }, [workflowId, navigate]);

  const exportPlan = useCallback(async () => {
    if (!workflowId) return;
    const data = await request<{ plan: Record<string, unknown> }>(
      `${API_BASE}/workflows/${workflowId}/export`
    );
    const blob = new Blob([JSON.stringify(data.plan, null, 2)], { type: "application/json" });
    const url = URL.createObjectURL(blob);
    const a = document.createElement("a");
    a.href = url; a.download = `workflow_${name}.json`;
    a.click();
    URL.revokeObjectURL(url);
  }, [workflowId, name]);

  if (loading) {
    return <div className="flex-1 flex items-center justify-center text-gray-400 animate-pulse">加载中…</div>;
  }

  const selectedNodeObj = nodes.find((n) => n.id === selectedNode);

  return (
    <div className="flex-1 flex flex-col overflow-hidden">
      {/* Toolbar */}
      <div className="flex items-center justify-between px-4 py-2 border-b border-gray-800 bg-gray-950 shrink-0">
        <div className="flex items-center gap-3">
          <button onClick={() => navigate("/workflows")} className="text-gray-500 hover:text-gray-300">
            <ArrowLeft size={18} />
          </button>
          <div className="flex items-center gap-2">
            <Workflow size={18} className="text-emerald-400" />
            <input
              value={name}
              onChange={(e) => setName(e.target.value)}
              placeholder="工作流名称"
              className="bg-transparent text-gray-200 text-sm font-medium border-b border-transparent hover:border-gray-700 focus:border-emerald-500 outline-none px-1 py-0.5 w-48"
            />
          </div>
        </div>
        <div className="flex items-center gap-2">
          {message && (
            <span className={`text-xs ${message.includes("失败") ? "text-red-400" : "text-emerald-400"}`}>
              {message}
            </span>
          )}
          {workflowId && (
            <>
              <button onClick={exportPlan} className="flex items-center gap-1 px-3 py-1.5 text-xs bg-gray-800 hover:bg-gray-700 text-gray-300 rounded-lg">
                <Download size={12} /> 导出
              </button>
              <button onClick={handleDelete} className="flex items-center gap-1 px-3 py-1.5 text-xs bg-red-900/20 hover:bg-red-900/40 text-red-400 rounded-lg">
                <Trash2 size={12} /> 删除
              </button>
            </>
          )}
          <button onClick={save} disabled={saving} className="flex items-center gap-1 px-4 py-1.5 text-xs bg-emerald-600 hover:bg-emerald-700 text-white rounded-lg disabled:opacity-50">
            <Save size={12} /> {saving ? "保存中…" : "保存"}
          </button>
        </div>
      </div>

      <div className="flex flex-1 overflow-hidden">
        {/* Left palette */}
        <div className="w-48 border-r border-gray-800 bg-gray-950 p-3 shrink-0 overflow-y-auto">
          <p className="text-xs text-gray-500 mb-3 uppercase tracking-wide">节点类型</p>
          <div className="space-y-1">
            {palette.map((item) => (
              <div
                key={item.type}
                draggable
                onDragStart={(e) => e.dataTransfer.setData("nodeType", item.type)}
                onClick={() => addNode(item.type, 200, 100 + palette.indexOf(item) * 80)}
                className="flex items-center gap-2 px-2.5 py-2 rounded-lg cursor-grab hover:bg-gray-800 transition-colors text-xs text-gray-400 hover:text-gray-200"
              >
                <span className="text-sm" style={{ color: item.color }}>
                  {ICON_MAP[item.icon] || <Play size={14} />}
                </span>
                <span>{item.label}</span>
              </div>
            ))}
          </div>
          <p className="text-xs text-gray-600 mt-4 leading-relaxed">
            拖拽节点到画布，或在画布上双击添加。点击节点后可从输出端连线。
          </p>
        </div>

        {/* Canvas */}
        <div
          ref={canvasRef}
          className="flex-1 relative overflow-auto bg-gray-950"
          style={{ backgroundImage: "radial-gradient(circle, #1f2937 1px, transparent 1px)", backgroundSize: "20px 20px" }}
          onClick={handleCanvasClick}
          onDrop={handleDrop}
          onDragOver={(e) => e.preventDefault()}
          onDoubleClick={(e) => {
            if (!canvasRef.current) return;
            const rect = canvasRef.current.getBoundingClientRect();
            addNode("agent", e.clientX - rect.left - 60, e.clientY - rect.top - 20);
          }}
        >
          {/* Edges */}
          <svg className="absolute inset-0 pointer-events-none" style={{ width: "100%", height: "100%" }}>
            {edges.map((edge) => {
              const src = nodes.find((n) => n.id === edge.source);
              const tgt = nodes.find((n) => n.id === edge.target);
              if (!src || !tgt) return null;
              const sx = src.x + 140;
              const sy = src.y + 22;
              const tx = tgt.x + 10;
              const ty = tgt.y + 22;
              return (
                <line
                  key={edge.id}
                  x1={sx} y1={sy} x2={tx} y2={ty}
                  stroke="#6366f1" strokeWidth="1.5"
                  markerEnd="url(#arrowhead)"
                />
              );
            })}
            <defs>
              <marker id="arrowhead" markerWidth="8" markerHeight="6" refX="8" refY="3" orient="auto">
                <polygon points="0 0, 8 3, 0 6" fill="#6366f1" />
              </marker>
            </defs>
          </svg>

          {/* Nodes */}
          {nodes.map((node) => {
            const isSelected = selectedNode === node.id;
            const isConnectingFrom = connecting === node.id;
            const paletteItem = palette.find((p) => p.type === node.type);
            const color = paletteItem?.color || "#6b7280";

            return (
              <div
                key={node.id}
                data-node={node.id}
                className="absolute cursor-pointer group"
                style={{ left: node.x, top: node.y, minWidth: 140 }}
                onClick={(e) => { e.stopPropagation(); setSelectedNode(node.id); }}
              >
                {/* Input port */}
                {node.type !== "schedule" && node.type !== "trigger" && (
                  <div
                    className={`absolute -left-2 top-5 w-3 h-3 rounded-full border-2 transition-colors cursor-crosshair ${
                      connecting ? "bg-emerald-500 border-emerald-500" : "bg-gray-800 border-gray-600 hover:border-emerald-400"
                    }`}
                    onClick={(e) => {
                      e.stopPropagation();
                      if (connecting) finishConnect(node.id);
                    }}
                    title="输入端口"
                  />
                )}

                {/* Node body */}
                <div
                  className={`rounded-lg border px-3 py-2 bg-gray-900 transition-all ${
                    isSelected ? "border-emerald-500 shadow-lg shadow-emerald-500/10" : "border-gray-700 hover:border-gray-600"
                  }`}
                  draggable
                  onDragStart={(e) => {
                    e.dataTransfer.setData("nodeType", "");
                    const startX = e.clientX;
                    const startY = e.clientY;
                    const moveHandler = (ev: MouseEvent) => {
                      const dx = ev.clientX - startX;
                      const dy = ev.clientY - startY;
                      moveNode(node.id, dx, dy);
                    };
                    const upHandler = () => {
                      document.removeEventListener("mousemove", moveHandler);
                      document.removeEventListener("mouseup", upHandler);
                    };
                    document.addEventListener("mousemove", moveHandler);
                    document.addEventListener("mouseup", upHandler);
                  }}
                >
                  <div className="flex items-center gap-1.5">
                    <span className="text-xs" style={{ color }}>{ICON_MAP[node.type] || <Play size={12} />}</span>
                    <span className="text-xs font-medium text-gray-300 truncate">{node.label}</span>
                  </div>
                </div>

                {/* Output port */}
                <div
                  className={`absolute -right-2 top-5 w-3 h-3 rounded-full border-2 transition-colors cursor-crosshair z-10 ${
                    isConnectingFrom ? "bg-amber-500 border-amber-500" : "bg-gray-800 border-gray-600 hover:border-amber-400"
                  }`}
                  onClick={(e) => {
                    e.stopPropagation();
                    startConnect(node.id);
                  }}
                  title="输出端口"
                />

                {/* Delete button */}
                {isSelected && (
                  <button
                    onClick={(e) => { e.stopPropagation(); deleteNode(node.id); }}
                    className="absolute -top-2 -right-2 w-5 h-5 rounded-full bg-red-600 text-white flex items-center justify-center text-xs opacity-0 group-hover:opacity-100 transition-opacity"
                    title="删除节点"
                  >
                    ×
                  </button>
                )}
              </div>
            );
          })}

          {nodes.length === 0 && (
            <div className="absolute inset-0 flex items-center justify-center pointer-events-none">
              <div className="text-center">
                <Workflow size={48} className="mx-auto mb-3 text-gray-800" />
                <p className="text-gray-600 text-sm">从左侧拖拽节点到画布，或双击画布添加节点</p>
              </div>
            </div>
          )}
        </div>

        {/* Right panel: properties */}
        {selectedNodeObj && (
          <div className="w-64 border-l border-gray-800 bg-gray-950 p-3 shrink-0 overflow-y-auto">
            <div className="flex items-center justify-between mb-3">
              <p className="text-xs text-gray-500 uppercase tracking-wide">节点属性</p>
              <button
                onClick={() => deleteNode(selectedNodeObj.id)}
                className="text-xs text-red-400 hover:text-red-300"
              >
                删除
              </button>
            </div>
            <div className="space-y-3">
              <div>
                <label className="text-xs text-gray-600 block mb-1">名称</label>
                <input
                  value={selectedNodeObj.label}
                  onChange={(e) => setNodes((prev) => prev.map((n) =>
                    n.id === selectedNodeObj.id ? { ...n, label: e.target.value } : n
                  ))}
                  className="w-full bg-gray-800 border border-gray-700 rounded px-2 py-1 text-xs text-gray-300 focus:border-emerald-500 outline-none"
                />
              </div>
              {selectedNodeObj.type === "schedule" && (
                <div>
                  <label className="text-xs text-gray-600 block mb-1">Cron 表达式</label>
                  <input
                    value={String(selectedNodeObj.data.schedule || "0 8 * * *")}
                    onChange={(e) => updateNodeData(selectedNodeObj.id, "schedule", e.target.value)}
                    className="w-full bg-gray-800 border border-gray-700 rounded px-2 py-1 text-xs text-gray-300 font-mono focus:border-emerald-500 outline-none"
                    placeholder="0 8 * * *"
                  />
                </div>
              )}
              {selectedNodeObj.type === "agent" && (
                <div>
                  <label className="text-xs text-gray-600 block mb-1">AI 提示词</label>
                  <textarea
                    value={String(selectedNodeObj.data.prompt || "")}
                    onChange={(e) => updateNodeData(selectedNodeObj.id, "prompt", e.target.value)}
                    rows={3}
                    className="w-full bg-gray-800 border border-gray-700 rounded px-2 py-1 text-xs text-gray-300 focus:border-emerald-500 outline-none resize-none"
                  />
                </div>
              )}
              {selectedNodeObj.type === "trigger" && (
                <div>
                  <label className="text-xs text-gray-600 block mb-1">触发事件</label>
                  <input
                    value={String(selectedNodeObj.data.event || "")}
                    onChange={(e) => updateNodeData(selectedNodeObj.id, "event", e.target.value)}
                    className="w-full bg-gray-800 border border-gray-700 rounded px-2 py-1 text-xs text-gray-300 focus:border-emerald-500 outline-none"
                    placeholder="inbox_email"
                  />
                </div>
              )}
              {selectedNodeObj.type === "action" && (
                <>
                  <div>
                    <label className="text-xs text-gray-600 block mb-1">工具名称</label>
                    <input
                      value={String(selectedNodeObj.data.tool || "")}
                      onChange={(e) => updateNodeData(selectedNodeObj.id, "tool", e.target.value)}
                      className="w-full bg-gray-800 border border-gray-700 rounded px-2 py-1 text-xs text-gray-300 focus:border-emerald-500 outline-none"
                    />
                  </div>
                  <div className="flex items-center gap-2">
                    <input
                      type="checkbox"
                      checked={!!selectedNodeObj.data.requires_approval}
                      onChange={(e) => updateNodeData(selectedNodeObj.id, "requires_approval", e.target.checked ? "true" : "")}
                      className="rounded"
                    />
                    <label className="text-xs text-gray-500">需要审批</label>
                  </div>
                </>
              )}
              {selectedNodeObj.type === "notification" && (
                <>
                  <div>
                    <label className="text-xs text-gray-600 block mb-1">标题</label>
                    <input
                      value={String(selectedNodeObj.data.title || "")}
                      onChange={(e) => updateNodeData(selectedNodeObj.id, "title", e.target.value)}
                      className="w-full bg-gray-800 border border-gray-700 rounded px-2 py-1 text-xs text-gray-300 focus:border-emerald-500 outline-none"
                    />
                  </div>
                  <div>
                    <label className="text-xs text-gray-600 block mb-1">内容</label>
                    <textarea
                      value={String(selectedNodeObj.data.content || "")}
                      onChange={(e) => updateNodeData(selectedNodeObj.id, "content", e.target.value)}
                      rows={2}
                      className="w-full bg-gray-800 border border-gray-700 rounded px-2 py-1 text-xs text-gray-300 focus:border-emerald-500 outline-none resize-none"
                    />
                  </div>
                </>
              )}
            </div>
          </div>
        )}
      </div>
    </div>
  );
}
