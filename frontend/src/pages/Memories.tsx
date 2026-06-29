import { useEffect, useState, useMemo, useRef } from "react";
import {
  listMemoriesGrouped,
  createMemory,
  deleteMemory,
  getMemoryGraph,
  ApiError,
  type MemoryRow,
  type MemoryGraph,
} from "../api/client";
import { useErrorStore } from "../stores/errorStore";
import { useQuickChat } from "../hooks/useQuickChat";
import Dialog from "../components/ui/Dialog";
import { Network, List } from "lucide-react";

function timeAgoShort(dateStr: string): string {
  const d = new Date(dateStr);
  const diff = Date.now() - d.getTime();
  const days = Math.floor(diff / 86400000);
  if (days > 30) return d.toLocaleDateString("zh-CN", { month: "short", day: "numeric" });
  if (days > 0) return `${days} 天前`;
  const hours = Math.floor(diff / 3600000);
  if (hours > 0) return `${hours} 小时前`;
  const mins = Math.floor(diff / 60000);
  if (mins > 0) return `${mins} 分钟前`;
  return "刚刚";
}

export default function MemoriesPage() {
  const [memories, setMemories] = useState<MemoryRow[]>([]);
  const [loading, setLoading] = useState(true);
  const [newContent, setNewContent] = useState("");
  const [deleteTarget, setDeleteTarget] = useState<MemoryRow | null>(null);
  const [viewMode, setViewMode] = useState<"list" | "graph">("list");
  const [graphData, setGraphData] = useState<MemoryGraph | null>(null);
  const [graphLoading, setGraphLoading] = useState(false);
  const addError = useErrorStore((s) => s.addError);
  const quickChat = useQuickChat();

  const grouped = useMemo(() => {
    const map: Record<string, MemoryRow[]> = {};
    for (const m of memories) {
      const cat = m.category || "其他";
      if (!map[cat]) map[cat] = [];
      map[cat].push(m);
    }
    return map;
  }, [memories]);

  const load = async () => {
    setLoading(true);
    try {
      const groupedData = await listMemoriesGrouped();
      setMemories(groupedData.memories);
    } catch (err) {
      const msg =
        err instanceof ApiError ? err.message : "加载记忆失败";
      addError(msg, "记忆");
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    load();
  }, []);

  const handleDelete = (m: MemoryRow) => {
    setDeleteTarget(m);
  };

  const confirmDelete = async () => {
    if (!deleteTarget) return;
    const id = deleteTarget.id;
    setDeleteTarget(null);
    try {
      await deleteMemory(id);
      load();
    } catch (err) {
      const msg =
        err instanceof ApiError ? err.message : "删除记忆失败";
      addError(msg, "记忆");
    }
  };

  const handleCreate = async () => {
    if (!newContent.trim()) return;
    try {
      await createMemory({ content: newContent.trim(), category: "fact" });
      setNewContent("");
      load();
    } catch (err) {
      const msg =
        err instanceof ApiError ? err.message : "创建记忆失败";
      addError(msg, "记忆");
    }
  };

  const handleContinueChat = (m: MemoryRow) => {
    quickChat({ title: "记忆讨论", prompt: `基于以下记忆继续讨论：\n${m.content}` });
  };

  const loadGraph = async () => {
    setGraphLoading(true);
    try {
      const data = await getMemoryGraph(30);
      setGraphData(data);
    } catch (err) {
      const msg = err instanceof ApiError ? err.message : "加载记忆图谱失败";
      addError(msg, "记忆");
    } finally {
      setGraphLoading(false);
    }
  };

  useEffect(() => {
    if (viewMode === "graph" && !graphData) {
      loadGraph();
    }
  }, [viewMode, graphData]);

  if (loading) {
    return (
      <div className="flex-1 flex items-center justify-center text-gray-500">
        加载中…
      </div>
    );
  }

  // 用户友好的分类映射
  const CATEGORY_LABELS: Record<string, { title: string; icon: string }> = {
    preference: { title: "你的偏好", icon: "💜" },
    habit: { title: "你的习惯", icon: "🔄" },
    fact: { title: "关于你", icon: "📌" },
    goal: { title: "你的目标", icon: "🎯" },
    event: { title: "你经历过的事", icon: "📅" },
    note: { title: "其他", icon: "📝" },
  };

  const getCategoryMeta = (cat: string) =>
    CATEGORY_LABELS[cat] ?? { title: cat, icon: "📝" };

  return (
    <div className="flex-1 overflow-y-auto p-6">
      <div className="max-w-4xl mx-auto space-y-8">
        <div className="flex items-center justify-between">
          <div>
            <h2 className="text-2xl font-bold mb-2">AI 对你的理解</h2>
            <p className="text-sm text-gray-500">
              这些是我从我们的对话中记住的。{memories.length > 0 && `共 ${memories.length} 条。`}
              每一条都让我更好地帮助你。
            </p>
          </div>
          <div className="flex gap-1 bg-gray-800 rounded-lg p-1">
            <button
              onClick={() => setViewMode("list")}
              className={`flex items-center gap-1.5 px-3 py-1.5 rounded text-sm transition-colors ${
                viewMode === "list"
                  ? "bg-gray-700 text-white"
                  : "text-gray-400 hover:text-gray-200"
              }`}
            >
              <List size={14} />
              列表
            </button>
            <button
              onClick={() => setViewMode("graph")}
              className={`flex items-center gap-1.5 px-3 py-1.5 rounded text-sm transition-colors ${
                viewMode === "graph"
                  ? "bg-gray-700 text-white"
                  : "text-gray-400 hover:text-gray-200"
              }`}
            >
              <Network size={14} />
              图谱
            </button>
          </div>
        </div>

        {viewMode === "list" ? (
          <>
            <div className="flex gap-2">
              <input
                value={newContent}
                onChange={(e) => setNewContent(e.target.value)}
                placeholder="告诉我一件关于你的事，我会记住..."
                className="flex-1 bg-gray-900 border border-gray-800 rounded-lg px-3 py-2 text-sm outline-none focus:border-emerald-600"
                onKeyDown={(e) => e.key === "Enter" && handleCreate()}
              />
              <button
                onClick={handleCreate}
                disabled={!newContent.trim()}
                className="px-4 py-2 bg-emerald-600 hover:bg-emerald-700 disabled:bg-gray-700 rounded-lg text-sm"
              >
                记住
              </button>
            </div>

            {Object.keys(grouped).length === 0 ? (
              <div className="text-center py-12">
                <div className="text-4xl mb-3">🧠</div>
                <p className="text-gray-500 text-sm">
                  我还没有记住任何事。开始一段对话，或者在上方告诉我关于你的事情。
                </p>
              </div>
            ) : (
              Object.entries(grouped).map(([category, items]) => {
                const meta = getCategoryMeta(category);
                return (
                  <section key={category}>
                    <h3 className="text-sm font-semibold text-gray-400 mb-3 flex items-center gap-1.5">
                      <span>{meta.icon}</span>
                      <span>{meta.title}</span>
                      <span className="text-gray-600">({items.length})</span>
                    </h3>
                    <ul className="space-y-2">
                      {items.map((m) => (
                        <li
                          key={m.id}
                          className="bg-gray-900 border border-gray-800 rounded-lg p-3 text-sm group"
                        >
                          <p className="text-gray-300">{m.content}</p>
                          <div className="flex items-center gap-3 mt-2">
                            {m.created_at && (
                              <span className="text-xs text-gray-600">
                                {timeAgoShort(m.created_at)}
                              </span>
                            )}
                            {m.origin === "claim" && (
                              <span className="text-xs text-indigo-500/60" title="这条记忆来自对话推断">
                                对话推断
                              </span>
                            )}
                            {m.origin === "self_report" && (
                              <span className="text-xs text-emerald-500/60" title="你直接告诉我的">
                                你告诉我的
                              </span>
                            )}
                            <button
                              onClick={() => handleContinueChat(m)}
                              className="text-xs text-emerald-500 hover:text-emerald-400 opacity-0 group-hover:opacity-100 transition-opacity"
                            >
                              继续聊
                            </button>
                            <button
                              onClick={() => handleDelete(m)}
                              className="text-xs text-red-500 hover:text-red-400 opacity-0 group-hover:opacity-100 transition-opacity"
                            >
                              忘掉
                            </button>
                          </div>
                        </li>
                      ))}
                    </ul>
                  </section>
                );
              })
            )}
          </>
        ) : (
          /* Graph View */
          <div className="bg-gray-900 border border-gray-800 rounded-lg p-4">
            {graphLoading ? (
              <div className="flex items-center justify-center h-96 text-gray-500">
                加载记忆图谱...
              </div>
            ) : graphData && graphData.nodes.length > 0 ? (
              <MemoryGraphView graph={graphData} />
            ) : (
              <div className="flex items-center justify-center h-96 text-gray-500">
                暂无记忆数据可显示
              </div>
            )}
          </div>
        )}
      </div>

      <Dialog
        open={!!deleteTarget}
        title="忘掉这条记忆？"
        description="确定让我忘掉这条记忆？此操作不可撤销。"
        confirmLabel="忘掉"
        variant="danger"
        onConfirm={confirmDelete}
        onCancel={() => setDeleteTarget(null)}
      />
    </div>
  );
}

// Simple force-directed graph layout
function useForceLayout(
  nodes: MemoryGraph["nodes"],
  edges: MemoryGraph["edges"],
  width: number,
  height: number
) {
  const [positions, setPositions] = useState<Record<string, { x: number; y: number }>>({});

  useEffect(() => {
    if (nodes.length === 0) return;

    // Initialize positions in a circle
    const pos: Record<string, { x: number; y: number; vx: number; vy: number }> = {};
    const cx = width / 2;
    const cy = height / 2;
    const radius = Math.min(width, height) * 0.35;

    nodes.forEach((node, i) => {
      const angle = (2 * Math.PI * i) / nodes.length;
      pos[node.id] = {
        x: cx + radius * Math.cos(angle),
        y: cy + radius * Math.sin(angle),
        vx: 0,
        vy: 0,
      };
    });

    // Simple force simulation
    const iterations = 50;
    for (let iter = 0; iter < iterations; iter++) {
      // Repulsion between all nodes
      for (let i = 0; i < nodes.length; i++) {
        for (let j = i + 1; j < nodes.length; j++) {
          const a = pos[nodes[i].id];
          const b = pos[nodes[j].id];
          const dx = b.x - a.x;
          const dy = b.y - a.y;
          const dist = Math.sqrt(dx * dx + dy * dy) || 1;
          const force = 5000 / (dist * dist);
          const fx = (dx / dist) * force;
          const fy = (dy / dist) * force;
          a.vx -= fx;
          a.vy -= fy;
          b.vx += fx;
          b.vy += fy;
        }
      }

      // Attraction along edges
      for (const edge of edges) {
        const a = pos[edge.source];
        const b = pos[edge.target];
        if (!a || !b) continue;
        const dx = b.x - a.x;
        const dy = b.y - a.y;
        const dist = Math.sqrt(dx * dx + dy * dy) || 1;
        const force = (dist - 100) * 0.01 * edge.weight;
        const fx = (dx / dist) * force;
        const fy = (dy / dist) * force;
        a.vx += fx;
        a.vy += fy;
        b.vx -= fx;
        b.vy -= fy;
      }

      // Apply velocities with damping
      for (const node of nodes) {
        const p = pos[node.id];
        p.vx *= 0.9;
        p.vy *= 0.9;
        p.x += p.vx;
        p.y += p.vy;
        // Keep within bounds
        p.x = Math.max(50, Math.min(width - 50, p.x));
        p.y = Math.max(50, Math.min(height - 50, p.y));
      }
    }

    // Extract final positions
    const finalPos: Record<string, { x: number; y: number }> = {};
    for (const node of nodes) {
      finalPos[node.id] = { x: pos[node.id].x, y: pos[node.id].y };
    }
    setPositions(finalPos);
  }, [nodes, edges, width, height]);

  return positions;
}

function MemoryGraphView({ graph }: { graph: MemoryGraph }) {
  const svgRef = useRef<SVGSVGElement>(null);
  const [hoveredNode, setHoveredNode] = useState<string | null>(null);
  const width = 700;
  const height = 500;

  const positions = useForceLayout(graph.nodes, graph.edges, width, height);

  const categoryColors: Record<string, string> = {
    fact: "#10b981",
    preference: "#8b5cf6",
    event: "#f59e0b",
    goal: "#3b82f6",
  };

  return (
    <div className="relative">
      <svg
        ref={svgRef}
        width={width}
        height={height}
        className="mx-auto"
        style={{ background: "#111827" }}
      >
        {/* Edges */}
        {graph.edges.map((edge, i) => {
          const source = positions[edge.source];
          const target = positions[edge.target];
          if (!source || !target) return null;
          const isHighlighted =
            hoveredNode === edge.source || hoveredNode === edge.target;
          return (
            <line
              key={i}
              x1={source.x}
              y1={source.y}
              x2={target.x}
              y2={target.y}
              stroke={isHighlighted ? "#60a5fa" : "#374151"}
              strokeWidth={isHighlighted ? 2 : 1}
              strokeOpacity={isHighlighted ? 0.8 : 0.3}
            />
          );
        })}

        {/* Nodes */}
        {graph.nodes.map((node) => {
          const pos = positions[node.id];
          if (!pos) return null;
          const color = categoryColors[node.category] || "#6b7280";
          const isHovered = hoveredNode === node.id;
          return (
            <g
              key={node.id}
              onMouseEnter={() => setHoveredNode(node.id)}
              onMouseLeave={() => setHoveredNode(null)}
              className="cursor-pointer"
            >
              <circle
                cx={pos.x}
                cy={pos.y}
                r={isHovered ? 12 : 8}
                fill={color}
                stroke={isHovered ? "#fff" : "none"}
                strokeWidth={2}
              />
              {isHovered && (
                <text
                  x={pos.x}
                  y={pos.y - 20}
                  textAnchor="middle"
                  fill="#fff"
                  fontSize={11}
                  className="pointer-events-none"
                >
                  {node.content.slice(0, 30)}
                  {node.content.length > 30 ? "..." : ""}
                </text>
              )}
            </g>
          );
        })}
      </svg>

      {/* Legend */}
      <div className="absolute top-4 right-4 bg-gray-800/80 rounded-lg p-3 text-xs">
        <div className="font-medium text-gray-300 mb-2">类别</div>
        {Object.entries(categoryColors).map(([cat, color]) => (
          <div key={cat} className="flex items-center gap-2 text-gray-400">
            <span
              className="w-3 h-3 rounded-full"
              style={{ backgroundColor: color }}
            />
            {cat}
          </div>
        ))}
      </div>

      {/* Stats */}
      <div className="absolute bottom-4 left-4 text-xs text-gray-500">
        {graph.nodes.length} 个记忆 · {graph.edges.length} 条关联
      </div>
    </div>
  );
}
