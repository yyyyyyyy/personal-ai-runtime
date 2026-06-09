import { useState, useEffect } from "react";
import { useChatStore } from "../stores/chatStore";

interface Goal {
  id: string;
  title: string;
  description: string | null;
  status: string;
  progress: number;
  importance: number;
  urgency: number;
  deadline: string | null;
  parent_id: string | null;
  created_at: string;
  last_activity_at: string | null;
  actions?: Action[];
  events?: Event[];
}

interface Action {
  id: string;
  goal_id: string;
  title: string;
  status: string;
  created_at: string;
  completed_at: string | null;
}

interface Event {
  id: string;
  type: string;
  summary: string;
  timestamp: string;
}

const API = "/api/goals";

function isStagnant(lastActivity: string | null, days: number = 3): boolean {
  if (!lastActivity) return true;
  const last = new Date(lastActivity);
  const now = new Date();
  return (now.getTime() - last.getTime()) > days * 86400000;
}

export default function GoalsPage() {
  const [goals, setGoals] = useState<Goal[]>([]);
  const [selectedGoal, setSelectedGoal] = useState<Goal | null>(null);
  const [showCreate, setShowCreate] = useState(false);
  const [newTitle, setNewTitle] = useState("");
  const [loading, setLoading] = useState(false);

  const activeConversationId = useChatStore((s) => s.activeConversationId);

  useEffect(() => {
    loadGoals();
  }, []);

  const loadGoals = async () => {
    try {
      const res = await fetch(`${API}/`);
      const data = await res.json();
      setGoals(data);
    } catch {
      // Backend may not be running
    }
  };

  const handleSelectGoal = async (goalId: string) => {
    try {
      const res = await fetch(`${API}/${goalId}`);
      const data = await res.json();
      setSelectedGoal(data);
    } catch {
      // ignore
    }
  };

  const handleCreateGoal = async () => {
    if (!newTitle.trim()) return;
    setLoading(true);
    try {
      await fetch(`${API}/`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ title: newTitle }),
      });
      setNewTitle("");
      setShowCreate(false);
      loadGoals();
    } catch {
      // ignore
    }
    setLoading(false);
  };

  const handleUpdateStatus = async (goalId: string, status: string) => {
    try {
      await fetch(`${API}/${goalId}`, {
        method: "PUT",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ status }),
      });
      loadGoals();
      if (selectedGoal?.id === goalId) handleSelectGoal(goalId);
    } catch {
      // ignore
    }
  };

  const handleCreateAction = async (goalId: string, title: string) => {
    if (!title.trim()) return;
    try {
      await fetch(`${API}/${goalId}/actions`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ title }),
      });
      handleSelectGoal(goalId);
      loadGoals();
    } catch {
      // ignore
    }
  };

  const handleToggleAction = async (goalId: string, actionId: string, currentStatus: string) => {
    const newStatus = currentStatus === "completed" ? "pending" : "completed";
    try {
      await fetch(`${API}/${goalId}/actions/${actionId}`, {
        method: "PUT",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ status: newStatus }),
      });
      handleSelectGoal(goalId);
      loadGoals();
    } catch {
      // ignore
    }
  };

  const statusLabels: Record<string, string> = {
    active: "进行中",
    paused: "已暂停",
    completed: "已完成",
  };

  return (
    <div className="flex h-full">
      {/* Goal list panel */}
      <div className="w-80 border-r border-gray-800 overflow-y-auto shrink-0">
        <div className="p-4 border-b border-gray-800 flex items-center justify-between">
          <h2 className="text-lg font-semibold">目标</h2>
          <button
            onClick={() => setShowCreate(true)}
            className="px-3 py-1.5 bg-emerald-600 hover:bg-emerald-700 rounded-lg text-sm transition-colors"
          >
            + 新建
          </button>
        </div>

        {showCreate && (
          <div className="p-3 border-b border-gray-800">
            <input
              autoFocus
              value={newTitle}
              onChange={(e) => setNewTitle(e.target.value)}
              onKeyDown={(e) => e.key === "Enter" && handleCreateGoal()}
              placeholder="目标名称..."
              className="w-full bg-gray-800 border border-gray-700 rounded-lg px-3 py-2 text-sm outline-none focus:border-emerald-600"
            />
            <div className="flex gap-2 mt-2">
              <button
                onClick={handleCreateGoal}
                disabled={loading || !newTitle.trim()}
                className="px-3 py-1 bg-emerald-600 hover:bg-emerald-700 rounded text-xs disabled:opacity-50"
              >
                {loading ? "创建中..." : "创建"}
              </button>
              <button
                onClick={() => { setShowCreate(false); setNewTitle(""); }}
                className="px-3 py-1 bg-gray-700 hover:bg-gray-600 rounded text-xs"
              >
                取消
              </button>
            </div>
          </div>
        )}

        <div className="p-2 space-y-1">
          {goals.map((goal) => (
            <div
              key={goal.id}
              onClick={() => handleSelectGoal(goal.id)}
              className={`p-3 rounded-lg cursor-pointer transition-colors ${
                selectedGoal?.id === goal.id
                  ? "bg-gray-800 border border-gray-700"
                  : "hover:bg-gray-800/50 border border-transparent"
              }`}
            >
              <div className="flex items-center gap-2">
                <span
                  className={`w-2 h-2 rounded-full shrink-0 ${
                    goal.status === "active"
                      ? "bg-emerald-500"
                      : goal.status === "completed"
                      ? "bg-blue-500"
                      : "bg-gray-500"
                  } ${isStagnant(goal.last_activity_at) && goal.status === "active" ? "ring-2 ring-amber-500" : ""}`}
                />
                <span className="text-sm font-medium truncate flex-1">{goal.title}</span>
              </div>
              {goal.deadline && (
                <div className="text-xs text-gray-500 mt-1 ml-4">
                  截止: {new Date(goal.deadline).toLocaleDateString("zh-CN")}
                </div>
              )}
            </div>
          ))}
          {goals.length === 0 && (
            <p className="text-sm text-gray-500 text-center py-8">暂无目标，点击「+ 新建」创建</p>
          )}
        </div>
      </div>

      {/* Goal detail panel */}
      <div className="flex-1 overflow-y-auto p-6">
        {selectedGoal ? (
          <div className="max-w-2xl">
            <div className="flex items-start justify-between mb-6">
              <div>
                <h2 className="text-2xl font-bold">{selectedGoal.title}</h2>
                <div className="flex items-center gap-2 mt-2">
                  <span className={`text-xs px-2 py-0.5 rounded-full ${
                    selectedGoal.status === "active" ? "bg-emerald-900/50 text-emerald-400" :
                    selectedGoal.status === "completed" ? "bg-blue-900/50 text-blue-400" :
                    "bg-gray-700 text-gray-400"
                  }`}>
                    {statusLabels[selectedGoal.status] || selectedGoal.status}
                  </span>
                  {isStagnant(selectedGoal.last_activity_at) && selectedGoal.status === "active" && (
                    <span className="text-xs px-2 py-0.5 rounded-full bg-amber-900/50 text-amber-400">
                      已停滞
                    </span>
                  )}
                </div>
              </div>
              <div className="flex gap-2">
                {selectedGoal.status === "active" && (
                  <>
                    <button
                      onClick={() => handleUpdateStatus(selectedGoal.id, "paused")}
                      className="px-3 py-1.5 text-xs bg-gray-700 hover:bg-gray-600 rounded"
                    >
                      暂停
                    </button>
                    <button
                      onClick={() => handleUpdateStatus(selectedGoal.id, "completed")}
                      className="px-3 py-1.5 text-xs bg-emerald-700 hover:bg-emerald-600 rounded"
                    >
                      完成
                    </button>
                  </>
                )}
                {selectedGoal.status === "paused" && (
                  <button
                    onClick={() => handleUpdateStatus(selectedGoal.id, "active")}
                    className="px-3 py-1.5 text-xs bg-emerald-700 hover:bg-emerald-600 rounded"
                  >
                    恢复
                  </button>
                )}
              </div>
            </div>

            {selectedGoal.description && (
              <p className="text-gray-400 mb-6">{selectedGoal.description}</p>
            )}

            {/* Actions */}
            <div className="mb-6">
              <h3 className="text-sm font-semibold text-gray-300 mb-3">
                行动步骤 ({selectedGoal.actions?.length || 0})
              </h3>
              <div className="space-y-2">
                {(selectedGoal.actions || []).map((action) => (
                  <div
                    key={action.id}
                    className="flex items-center gap-3 p-3 bg-gray-800/50 rounded-lg"
                  >
                    <input
                      type="checkbox"
                      checked={action.status === "completed"}
                      onChange={() => handleToggleAction(selectedGoal.id, action.id, action.status)}
                      className="w-4 h-4 rounded border-gray-600 bg-gray-700 accent-emerald-600"
                    />
                    <span className={`text-sm flex-1 ${action.status === "completed" ? "line-through text-gray-500" : ""}`}>
                      {action.title}
                    </span>
                  </div>
                ))}
                <NewActionInput onAdd={(title) => handleCreateAction(selectedGoal.id, title)} />
              </div>
            </div>

            {/* Events */}
            {selectedGoal.events && selectedGoal.events.length > 0 && (
              <div>
                <h3 className="text-sm font-semibold text-gray-300 mb-3">相关事件</h3>
                <div className="space-y-2">
                  {selectedGoal.events.map((event) => (
                    <div key={event.id} className="flex items-center gap-2 text-xs text-gray-500">
                      <span className="text-gray-600">
                        {new Date(event.timestamp).toLocaleString("zh-CN")}
                      </span>
                      <span>{event.summary}</span>
                    </div>
                  ))}
                </div>
              </div>
            )}
          </div>
        ) : (
          <div className="flex items-center justify-center h-full text-gray-500">
            选择一个目标查看详情
          </div>
        )}
      </div>
    </div>
  );
}

function NewActionInput({ onAdd }: { onAdd: (title: string) => void }) {
  const [value, setValue] = useState("");

  const handleSubmit = () => {
    if (value.trim()) {
      onAdd(value.trim());
      setValue("");
    }
  };

  return (
    <div className="flex gap-2">
      <input
        value={value}
        onChange={(e) => setValue(e.target.value)}
        onKeyDown={(e) => e.key === "Enter" && handleSubmit()}
        placeholder="添加行动步骤..."
        className="flex-1 bg-gray-800 border border-gray-700 rounded-lg px-3 py-2 text-sm outline-none focus:border-emerald-600"
      />
      <button
        onClick={handleSubmit}
        disabled={!value.trim()}
        className="px-3 py-2 bg-gray-700 hover:bg-gray-600 rounded-lg text-sm disabled:opacity-50"
      >
        添加
      </button>
    </div>
  );
}
