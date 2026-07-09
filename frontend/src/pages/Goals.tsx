import { useState, useEffect } from "react";
import { useNavigate, useParams } from "react-router-dom";
import {
  listGoals,
  getGoal,
  createGoal,
  updateGoal,
  deleteGoal,
  createGoalAction,
  updateGoalAction,
  decomposeGoal,
  ApiError,
  type Goal,
} from "../api/client";
import { useErrorStore } from "../stores/errorStore";
import { useQuickChat } from "../hooks/useQuickChat";
import Badge from "../components/ui/Badge";
import Button from "../components/ui/Button";
import Dialog from "../components/ui/Dialog";
import EmptyState from "../components/ui/EmptyState";
import { Input } from "../components/ui/Input";
import { timeAgo, isStagnant } from "../utils/timeUtils";
import { Sparkles } from "lucide-react";

export default function GoalsPage() {
  const { goalId: urlGoalId } = useParams();
  const navigate = useNavigate();
  const [goals, setGoals] = useState<Goal[]>([]);
  const [selectedGoal, setSelectedGoal] = useState<Goal | null>(null);
  const [showCreate, setShowCreate] = useState(false);
  const [newTitle, setNewTitle] = useState("");
  const [loading, setLoading] = useState(false);
  const [deleteTarget, setDeleteTarget] = useState<Goal | null>(null);
  const [deleting, setDeleting] = useState(false);
  const [goalNotFound, setGoalNotFound] = useState(false);
  const [suggestedSteps, setSuggestedSteps] = useState<string[]>([]);
  const [decomposing, setDecomposing] = useState(false);
  const addError = useErrorStore((s) => s.addError);
  const quickChat = useQuickChat();

  useEffect(() => {
    loadGoals();
  }, []);

  useEffect(() => {
    if (urlGoalId) {
      loadGoalById(urlGoalId);
    } else {
      setSelectedGoal(null);
      setGoalNotFound(false);
    }
  }, [urlGoalId]);

  const loadGoals = async () => {
    try {
      const data = await listGoals();
      setGoals(data);
    } catch (err) {
      const msg = err instanceof ApiError ? err.message : "加载目标失败";
      addError(msg, "目标");
    }
  };

  const loadGoalById = async (goalId: string) => {
    setGoalNotFound(false);
    try {
      const data = await getGoal(goalId);
      setSelectedGoal(data);
    } catch (err) {
      if (err instanceof ApiError && err.status === 404) {
        setGoalNotFound(true);
        setSelectedGoal(null);
      }
      const msg = err instanceof ApiError ? err.message : "加载目标详情失败";
      addError(msg, "目标");
    }
  };

  const handleSelectGoal = (goalId: string) => {
    navigate(`/goals/${goalId}`);
  };

  const handleStartChatAboutGoal = (goal: Goal) => {
    quickChat({
      title: `目标：${goal.title}`,
      prompt: `我想讨论目标「${goal.title}」${goal.description ? `：${goal.description}` : ""}。当前进度 ${goal.progress}%，请帮我分析下一步行动。`,
    });
  };

  const handleCreateGoal = async () => {
    if (!newTitle.trim()) return;
    setLoading(true);
    try {
      await createGoal({ title: newTitle });
      setNewTitle("");
      setShowCreate(false);
      loadGoals();
    } catch (err) {
      const msg = err instanceof ApiError ? err.message : "创建目标失败";
      addError(msg, "目标");
    }
    setLoading(false);
  };

  const handleUpdateStatus = async (goalId: string, status: string) => {
    try {
      await updateGoal(goalId, { status });
      loadGoals();
      if (selectedGoal?.id === goalId) loadGoalById(goalId);
    } catch (err) {
      const msg = err instanceof ApiError ? err.message : "更新目标状态失败";
      addError(msg, "目标");
    }
  };

  const handleCreateAction = async (goalId: string, title: string) => {
    if (!title.trim()) return;
    try {
      await createGoalAction(goalId, title);
      loadGoalById(goalId);
      loadGoals();
    } catch (err) {
      const msg = err instanceof ApiError ? err.message : "创建行动步骤失败";
      addError(msg, "目标");
    }
  };

  const handleToggleAction = async (goalId: string, actionId: string, currentStatus: string) => {
    const newStatus = currentStatus === "completed" ? "pending" : "completed";
    try {
      await updateGoalAction(goalId, actionId, { status: newStatus });
      loadGoalById(goalId);
      loadGoals();
    } catch (err) {
      const msg = err instanceof ApiError ? err.message : "更新行动步骤失败";
      addError(msg, "目标");
    }
  };

  const handleDeleteGoal = async () => {
    if (!deleteTarget) return;
    const goalId = deleteTarget.id;
    setDeleting(true);
    try {
      await deleteGoal(goalId);
      setDeleteTarget(null);
      if (selectedGoal?.id === goalId) {
        setSelectedGoal(null);
        navigate("/goals");
      }
      await loadGoals();
    } catch (err) {
      const msg = err instanceof ApiError ? err.message : "删除目标失败";
      addError(msg, "目标");
    } finally {
      setDeleting(false);
    }
  };

  const handleDecomposeGoal = async () => {
    if (!selectedGoal) return;
    setDecomposing(true);
    setSuggestedSteps([]);
    try {
      const result = await decomposeGoal(selectedGoal.id);
      setSuggestedSteps(result.steps || []);
    } catch (err) {
      const msg = err instanceof ApiError ? err.message : "AI 拆解失败";
      addError(msg, "目标");
    } finally {
      setDecomposing(false);
    }
  };

  const handleAddSuggestedStep = async (title: string) => {
    if (!selectedGoal) return;
    await handleCreateAction(selectedGoal.id, title);
    // Remove from suggested steps
    setSuggestedSteps((prev) => prev.filter((s) => s !== title));
  };

  const handleAddAllSuggestedSteps = async () => {
    if (!selectedGoal) return;
    for (const step of suggestedSteps) {
      await handleCreateAction(selectedGoal.id, step);
    }
    setSuggestedSteps([]);
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
          <Button size="sm" onClick={() => setShowCreate(true)}>
            + 新建
          </Button>
        </div>

        {showCreate && (
          <div className="p-3 border-b border-gray-800">
            <Input
              autoFocus
              value={newTitle}
              onChange={(e) => setNewTitle(e.target.value)}
              onKeyDown={(e) => e.key === "Enter" && handleCreateGoal()}
              placeholder="目标名称..."
              className="w-full"
            />
            <div className="flex gap-2 mt-2">
              <Button size="sm" onClick={handleCreateGoal} disabled={loading || !newTitle.trim()}>
                {loading ? "创建中..." : "创建"}
              </Button>
              <Button
                size="sm"
                variant="secondary"
                onClick={() => {
                  setShowCreate(false);
                  setNewTitle("");
                }}
              >
                取消
              </Button>
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
              {goal.last_activity_at && (
                <div className="text-xs text-gray-600 mt-1 ml-4">
                  上次活动: {timeAgo(goal.last_activity_at)}
                </div>
              )}
              {goal.deadline && (
                <div className="text-xs text-gray-500 mt-1 ml-4">
                  截止: {new Date(goal.deadline).toLocaleDateString("zh-CN")}
                </div>
              )}
              <div className="mt-2 ml-4 h-1 bg-gray-800 rounded-full overflow-hidden">
                <div
                  className="h-full bg-emerald-600 rounded-full"
                  style={{ width: `${Math.min(goal.progress, 100)}%` }}
                />
              </div>
            </div>
          ))}
          {goals.length === 0 && (
            <EmptyState
              title="暂无目标"
              description="创建第一个目标，让 AI 帮你追踪进度"
              action={
                <Button size="sm" onClick={() => setShowCreate(true)}>
                  创建目标
                </Button>
              }
            />
          )}
        </div>
      </div>

      {/* Goal detail panel */}
      <div className="flex-1 overflow-y-auto p-6">
        {goalNotFound ? (
          <EmptyState
            title="目标不存在"
            description="该目标可能已被删除，或链接无效。请从左侧列表选择其他目标。"
            action={
              <Button size="sm" onClick={() => navigate("/goals")}>
                返回列表
              </Button>
            }
          />
        ) : selectedGoal ? (
          <div className="max-w-2xl">
            <div className="flex items-start justify-between mb-6">
              <div>
                <h2 className="text-2xl font-bold">{selectedGoal.title}</h2>
                <div className="flex items-center gap-2 mt-2">
                  <Badge
                    tone={
                      selectedGoal.status === "active"
                        ? "success"
                        : selectedGoal.status === "completed"
                          ? "info"
                          : "default"
                    }
                  >
                    {statusLabels[selectedGoal.status] || selectedGoal.status}
                  </Badge>
                  {isStagnant(selectedGoal.last_activity_at) &&
                    selectedGoal.status === "active" && <Badge tone="warning">已停滞</Badge>}
                </div>
                <div className="mt-3 h-2 bg-gray-800 rounded-full overflow-hidden max-w-xs">
                  <div
                    className="h-full bg-emerald-600 rounded-full transition-all"
                    style={{ width: `${Math.min(selectedGoal.progress, 100)}%` }}
                  />
                </div>
                <p className="text-xs text-gray-500 mt-1">进度 {selectedGoal.progress}%</p>
              </div>
              <div className="flex gap-2">
                <Button size="sm" onClick={() => handleStartChatAboutGoal(selectedGoal)}>
                  就此目标对话
                </Button>
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
                <Button size="sm" variant="danger" onClick={() => setDeleteTarget(selectedGoal)}>
                  删除
                </Button>
              </div>
            </div>

            {selectedGoal.description && (
              <p className="text-gray-400 mb-6">{selectedGoal.description}</p>
            )}

            {/* Actions */}
            <div className="mb-6">
              <div className="flex items-center justify-between mb-3">
                <h3 className="text-sm font-semibold text-gray-300">
                  行动步骤 ({selectedGoal.actions?.length || 0})
                </h3>
                <button
                  onClick={handleDecomposeGoal}
                  disabled={decomposing}
                  className="flex items-center gap-1.5 px-3 py-1.5 text-xs bg-purple-700/30 hover:bg-purple-700/50 text-purple-300 rounded-lg border border-purple-700/50 disabled:opacity-50 transition-colors"
                >
                  <Sparkles size={12} />
                  {decomposing ? "AI 拆解中..." : "AI 拆解"}
                </button>
              </div>

              {/* AI Suggested Steps */}
              {suggestedSteps.length > 0 && (
                <div className="mb-4 p-3 bg-purple-900/20 border border-purple-700/30 rounded-lg">
                  <div className="flex items-center justify-between mb-2">
                    <span className="text-xs text-purple-300 font-medium">
                      ✨ AI 建议的行动步骤
                    </span>
                    <button
                      onClick={handleAddAllSuggestedSteps}
                      className="text-xs px-2 py-1 bg-purple-700/50 hover:bg-purple-700/70 rounded text-purple-200"
                    >
                      全部添加
                    </button>
                  </div>
                  <div className="space-y-1.5">
                    {suggestedSteps.map((step, idx) => (
                      <div key={idx} className="flex items-center gap-2 text-sm text-gray-300">
                        <span className="text-purple-400">•</span>
                        <span className="flex-1">{step}</span>
                        <button
                          onClick={() => handleAddSuggestedStep(step)}
                          className="text-xs px-2 py-0.5 bg-gray-700 hover:bg-gray-600 rounded text-gray-300"
                        >
                          添加
                        </button>
                      </div>
                    ))}
                  </div>
                </div>
              )}

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
                    <span
                      className={`text-sm flex-1 ${action.status === "completed" ? "line-through text-gray-500" : ""}`}
                    >
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
          <EmptyState title="选择一个目标" description="从左侧列表选择目标查看详情与行动步骤" />
        )}
      </div>

      <Dialog
        open={!!deleteTarget}
        title="删除目标"
        description={
          deleteTarget
            ? `确定删除目标「${deleteTarget.title}」？关联的行动步骤将一并删除，此操作不可撤销。`
            : undefined
        }
        confirmLabel={deleting ? "删除中…" : "删除"}
        variant="danger"
        onConfirm={handleDeleteGoal}
        onCancel={() => !deleting && setDeleteTarget(null)}
      />
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
