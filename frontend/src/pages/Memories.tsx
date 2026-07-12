import { useEffect, useMemo, useState } from "react";
import { useSearchParams } from "react-router-dom";
import { useQueryClient } from "@tanstack/react-query";
import {
  createMemory,
  deleteMemory,
  updateMemory,
  ratifyMemory,
  rejectMemory,
  getMemoryGraph,
  ApiError,
  type MemoryRow,
  type MemoryGraph,
} from "../api/client";
import { useErrorStore } from "../stores/errorStore";
import { useQuickChat } from "../hooks/useQuickChat";
import { useMemoriesGroupedQuery } from "../hooks/useMemoriesQuery";
import { queryKeys } from "../hooks/useWsInvalidationBridge";
import { PortraitPanel } from "./Portrait";
import Dialog from "../components/ui/Dialog";
import MemoryGraphView from "../components/memories/MemoryGraphView";
import MemoryListItem, { getCategoryMeta } from "../components/memories/MemoryListItem";
import MemoryProvenanceDialog from "../components/memories/MemoryProvenanceDialog";
import { Network, List, User } from "lucide-react";

type ViewMode = "list" | "graph" | "portrait";

export default function MemoriesPage() {
  const queryClient = useQueryClient();
  const [searchParams, setSearchParams] = useSearchParams();
  const tabParam = searchParams.get("tab");
  const viewMode: ViewMode =
    tabParam === "portrait" ? "portrait" : tabParam === "graph" ? "graph" : "list";
  const setViewMode = (mode: ViewMode) => {
    if (mode === "list") {
      setSearchParams({}, { replace: true });
    } else {
      setSearchParams({ tab: mode }, { replace: true });
    }
  };

  const { data, isLoading: loading, error: loadError } = useMemoriesGroupedQuery();
  const memories = data?.memories ?? [];
  const addError = useErrorStore((s) => s.addError);
  const quickChat = useQuickChat();

  const [newContent, setNewContent] = useState("");
  const [deleteTarget, setDeleteTarget] = useState<MemoryRow | null>(null);
  const [editTarget, setEditTarget] = useState<MemoryRow | null>(null);
  const [editContent, setEditContent] = useState("");
  const [editCategory, setEditCategory] = useState("");
  const [provenanceTarget, setProvenanceTarget] = useState<MemoryRow | null>(null);
  const [graphData, setGraphData] = useState<MemoryGraph | null>(null);
  const [graphLoading, setGraphLoading] = useState(false);

  const invalidateMemories = () => {
    void queryClient.invalidateQueries({ queryKey: queryKeys.memories });
  };

  const grouped = useMemo(() => {
    const map: Record<string, MemoryRow[]> = {};
    for (const m of memories) {
      const cat = m.category || "其他";
      if (!map[cat]) map[cat] = [];
      map[cat].push(m);
    }
    return map;
  }, [memories]);

  useEffect(() => {
    if (loadError) {
      const msg = loadError instanceof ApiError ? loadError.message : "加载记忆失败";
      addError(msg, "记忆");
    }
  }, [loadError, addError]);

  // ── Mutations (manual invalidate; useMigration migration tracked separately) ──

  const handleCreate = async () => {
    if (!newContent.trim()) return;
    try {
      await createMemory({ content: newContent.trim(), category: "fact" });
      setNewContent("");
      invalidateMemories();
    } catch (err) {
      addError(err instanceof ApiError ? err.message : "创建记忆失败", "记忆");
    }
  };

  const confirmDelete = async () => {
    if (!deleteTarget) return;
    const id = deleteTarget.id;
    setDeleteTarget(null);
    try {
      await deleteMemory(id);
      invalidateMemories();
    } catch (err) {
      addError(err instanceof ApiError ? err.message : "删除记忆失败", "记忆");
    }
  };

  const confirmEdit = async () => {
    if (!editTarget || !editContent.trim()) return;
    const id = editTarget.id;
    setEditTarget(null);
    try {
      await updateMemory(id, { content: editContent.trim(), category: editCategory || undefined });
      invalidateMemories();
    } catch (err) {
      addError(err instanceof ApiError ? err.message : "更新记忆失败", "记忆");
    }
  };

  const handleRatify = async (m: MemoryRow) => {
    try {
      await ratifyMemory(m.id);
      invalidateMemories();
    } catch (err) {
      addError(err instanceof ApiError ? err.message : "确认记忆失败", "记忆");
    }
  };

  const handleReject = async (m: MemoryRow) => {
    try {
      await rejectMemory(m.id);
      invalidateMemories();
    } catch (err) {
      addError(err instanceof ApiError ? err.message : "拒绝记忆失败", "记忆");
    }
  };

  const handleEdit = (m: MemoryRow) => {
    setEditTarget(m);
    setEditContent(m.content);
    setEditCategory(m.category || "fact");
  };

  const handleContinueChat = (m: MemoryRow) => {
    quickChat({ title: "记忆讨论", prompt: `基于以下记忆继续讨论：\n${m.content}` });
  };

  // ── Graph loading (lazy on first switch to graph view) ──

  useEffect(() => {
    if (viewMode !== "graph" || graphData) return;
    let cancelled = false;
    setGraphLoading(true);
    (async () => {
      try {
        const data = await getMemoryGraph(30);
        if (!cancelled) setGraphData(data);
      } catch (err) {
        if (!cancelled) {
          addError(err instanceof ApiError ? err.message : "加载记忆图谱失败", "记忆");
        }
      } finally {
        if (!cancelled) setGraphLoading(false);
      }
    })();
    return () => {
      cancelled = true;
    };
  }, [viewMode, graphData, addError]);

  if (loading) {
    return <div className="flex-1 flex items-center justify-center text-gray-500">加载中…</div>;
  }

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
                viewMode === "list" ? "bg-gray-700 text-white" : "text-gray-400 hover:text-gray-200"
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
            <button
              onClick={() => setViewMode("portrait")}
              className={`flex items-center gap-1.5 px-3 py-1.5 rounded text-sm transition-colors ${
                viewMode === "portrait"
                  ? "bg-gray-700 text-white"
                  : "text-gray-400 hover:text-gray-200"
              }`}
            >
              <User size={14} />
              画像
            </button>
          </div>
        </div>

        {viewMode === "portrait" ? (
          <PortraitPanel compact />
        ) : viewMode === "list" ? (
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
                        <MemoryListItem
                          key={m.id}
                          memory={m}
                          onRatify={handleRatify}
                          onReject={handleReject}
                          onEdit={handleEdit}
                          onDelete={setDeleteTarget}
                          onContinueChat={handleContinueChat}
                          onShowProvenance={setProvenanceTarget}
                        />
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

      {editTarget && (
        <div
          className="fixed inset-0 bg-black/50 flex items-center justify-center z-50"
          onClick={() => setEditTarget(null)}
        >
          <div
            className="bg-gray-800 border border-gray-700 rounded-xl p-6 w-96 max-w-[90vw] space-y-4"
            onClick={(e) => e.stopPropagation()}
          >
            <h3 className="text-lg font-semibold text-white">编辑记忆</h3>
            <p className="text-xs text-gray-500">更新会保留旧版本——可在"来源"查看完整版本演进</p>
            <div className="space-y-3">
              <div>
                <label className="text-xs text-gray-400 mb-1 block">内容</label>
                <input
                  value={editContent}
                  onChange={(e) => setEditContent(e.target.value)}
                  className="w-full bg-gray-700 rounded-lg px-3 py-2 text-sm text-white border border-gray-600"
                  placeholder="记忆内容"
                  autoFocus
                />
              </div>
              <div>
                <label className="text-xs text-gray-400 mb-1 block">分类</label>
                <input
                  value={editCategory}
                  onChange={(e) => setEditCategory(e.target.value)}
                  className="w-full bg-gray-700 rounded-lg px-3 py-2 text-sm text-white border border-gray-600"
                  placeholder="如 fact, preference, habit"
                />
              </div>
            </div>
            <div className="flex gap-2 justify-end">
              <button
                onClick={() => setEditTarget(null)}
                className="px-3 py-1.5 bg-gray-700 hover:bg-gray-600 rounded-lg text-sm"
              >
                取消
              </button>
              <button
                onClick={confirmEdit}
                className="px-3 py-1.5 bg-emerald-600 hover:bg-emerald-700 rounded-lg text-sm"
              >
                保存
              </button>
            </div>
          </div>
        </div>
      )}

      {provenanceTarget && (
        <MemoryProvenanceDialog
          target={provenanceTarget}
          onClose={() => setProvenanceTarget(null)}
        />
      )}
    </div>
  );
}
