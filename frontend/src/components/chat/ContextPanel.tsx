import { useEffect, useState } from "react";
import { useNavigate } from "react-router-dom";
import {
  listGoals,
  searchMemories,
  listPendingApprovals,
  type Goal,
  type MemoryRow,
  type Approval,
} from "../../api/client";
import { useErrorStore } from "../../stores/errorStore";

interface ToolResult {
  tool_name: string;
  tool_call_id: string;
  content: string;
}

interface Props {
  lastUserMessage?: string;
  toolResults?: ToolResult[];
  open: boolean;
  onToggle: () => void;
}

export default function ContextPanel({
  lastUserMessage,
  toolResults = [],
  open,
  onToggle,
}: Props) {
  const navigate = useNavigate();
  const addError = useErrorStore((s) => s.addError);
  const [goals, setGoals] = useState<Goal[]>([]);
  const [memories, setMemories] = useState<MemoryRow[]>([]);
  const [approvals, setApprovals] = useState<Approval[]>([]);

  useEffect(() => {
    if (!open) return;
    loadContext();
  }, [open, lastUserMessage]);

  const loadContext = async () => {
    try {
      const allGoals = await listGoals();
      const active = allGoals
        .filter((g) => g.status === "active")
        .sort((a, b) => {
          const ta = a.last_activity_at
            ? new Date(a.last_activity_at).getTime()
            : 0;
          const tb = b.last_activity_at
            ? new Date(b.last_activity_at).getTime()
            : 0;
          return tb - ta;
        })
        .slice(0, 3);
      setGoals(active);
    } catch (err) {
      addError("加载目标失败", "上下文");
    }

    if (lastUserMessage && lastUserMessage.length > 5) {
      try {
        const q = lastUserMessage.slice(0, 50);
        const results = await searchMemories(q, 3);
        setMemories(results);
      } catch {
        // optional
      }
    }

    try {
      const pending = await listPendingApprovals();
      setApprovals(pending);
    } catch {
      // optional
    }
  };

  const recentTools = toolResults.slice(-3).reverse();

  if (!open) {
    return (
      <button
        onClick={onToggle}
        className="absolute top-3 right-3 z-10 px-2 py-1 text-xs bg-gray-800 hover:bg-gray-700 rounded-lg text-gray-400 border border-gray-700"
        title="展开上下文面板"
      >
        上下文
      </button>
    );
  }

  return (
    <aside className="w-72 border-l border-gray-800 bg-gray-900/50 overflow-y-auto shrink-0 flex flex-col">
      <div className="p-3 border-b border-gray-800 flex items-center justify-between">
        <h3 className="text-sm font-medium text-gray-300">上下文</h3>
        <button
          onClick={onToggle}
          className="text-xs text-gray-500 hover:text-gray-300"
        >
          收起
        </button>
      </div>

      <div className="p-3 space-y-4 flex-1">
        {approvals.length > 0 && (
          <section>
            <h4 className="text-xs text-amber-400 mb-2">待审批 ({approvals.length})</h4>
            {approvals.map((a) => (
              <div
                key={a.id}
                className="text-xs text-gray-400 p-2 bg-amber-900/20 rounded-lg mb-1"
              >
                {a.action || "未知操作"}
              </div>
            ))}
          </section>
        )}

        <section>
          <h4 className="text-xs text-gray-500 mb-2">活跃目标</h4>
          {goals.length === 0 ? (
            <p className="text-xs text-gray-600">暂无活跃目标</p>
          ) : (
            goals.map((g) => (
              <button
                key={g.id}
                onClick={() => navigate(`/goals/${g.id}`)}
                className="block w-full text-left text-xs text-gray-300 p-2 hover:bg-gray-800 rounded-lg mb-1 truncate"
              >
                {g.title}
              </button>
            ))
          )}
        </section>

        {memories.length > 0 && (
          <section>
            <h4 className="text-xs text-gray-500 mb-2">相关记忆</h4>
            {memories.map((m) => (
              <div
                key={m.id}
                className="text-xs text-gray-400 p-2 bg-gray-800/50 rounded-lg mb-1 line-clamp-2"
              >
                {m.content}
              </div>
            ))}
          </section>
        )}

        {recentTools.length > 0 && (
          <section>
            <h4 className="text-xs text-gray-500 mb-2">最近工具</h4>
            {recentTools.map((t, i) => (
              <div
                key={`${t.tool_call_id}-${i}`}
                className="text-xs text-gray-400 p-2 bg-gray-800/50 rounded-lg mb-1 truncate"
              >
                {t.tool_name}
              </div>
            ))}
          </section>
        )}
      </div>
    </aside>
  );
}
