import { useEffect, useState, useMemo } from "react";
import {
  listMemoriesGrouped,
  createMemory,
  deleteMemory,
  ApiError,
  type MemoryRow,
} from "../api/client";
import { useErrorStore } from "../stores/errorStore";
import { useQuickChat } from "../hooks/useQuickChat";
import Dialog from "../components/ui/Dialog";

export default function MemoriesPage() {
  const [memories, setMemories] = useState<MemoryRow[]>([]);
  const [loading, setLoading] = useState(true);
  const [newContent, setNewContent] = useState("");
  const [deleteTarget, setDeleteTarget] = useState<MemoryRow | null>(null);
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

  if (loading) {
    return (
      <div className="flex-1 flex items-center justify-center text-gray-500">
        加载中…
      </div>
    );
  }

  return (
    <div className="flex-1 overflow-y-auto p-6">
      <div className="max-w-3xl mx-auto space-y-8">
        <div>
          <h2 className="text-2xl font-bold mb-2">记忆</h2>
          <p className="text-sm text-gray-500">
            系统从对话与活动中提取的长期记忆。
          </p>
        </div>

        <div className="flex gap-2">
          <input
            value={newContent}
            onChange={(e) => setNewContent(e.target.value)}
            placeholder="手动添加记忆..."
            className="flex-1 bg-gray-900 border border-gray-800 rounded-lg px-3 py-2 text-sm outline-none focus:border-emerald-600"
          />
          <button
            onClick={handleCreate}
            disabled={!newContent.trim()}
            className="px-4 py-2 bg-emerald-600 hover:bg-emerald-700 disabled:bg-gray-700 rounded-lg text-sm"
          >
            添加
          </button>
        </div>

        {Object.keys(grouped).length === 0 ? (
          <p className="text-gray-600 text-sm">暂无记忆。</p>
        ) : (
          Object.entries(grouped).map(([category, items]) => (
            <section key={category}>
              <h3 className="text-sm font-semibold text-gray-400 mb-3 capitalize">
                {category} ({items.length})
              </h3>
              <ul className="space-y-2">
                {items.map((m) => (
                  <li
                    key={m.id}
                    className="bg-gray-900 border border-gray-800 rounded-lg p-3 text-sm"
                  >
                    <p className="text-gray-300">{m.content}</p>
                    <div className="flex items-center gap-3 mt-2">
                      {m.confidence != null && (
                        <span className="text-xs text-gray-500">
                          置信度 {m.confidence.toFixed(2)}
                        </span>
                      )}
                      <button
                        onClick={() => handleContinueChat(m)}
                        className="text-xs text-emerald-500 hover:text-emerald-400"
                      >
                        继续聊
                      </button>
                      <button
                        onClick={() => handleDelete(m)}
                        className="text-xs text-red-500 hover:text-red-400"
                      >
                        删除
                      </button>
                    </div>
                  </li>
                ))}
              </ul>
            </section>
          ))
        )}
      </div>

      <Dialog
        open={!!deleteTarget}
        title="删除记忆"
        description="确定删除这条记忆？此操作不可撤销。"
        confirmLabel="删除"
        variant="danger"
        onConfirm={confirmDelete}
        onCancel={() => setDeleteTarget(null)}
      />
    </div>
  );
}
