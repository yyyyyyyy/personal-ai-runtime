import { useEffect, useState } from "react";
import {
  getInboxDigest,
  listInboxEmails,
  triggerInboxPoll,
  ApiError,
  type InboxEmail,
} from "../api/client";
import { useErrorStore } from "../stores/errorStore";
import { useQuickChat } from "../hooks/useQuickChat";
import Button from "../components/ui/Button";
import Card from "../components/ui/Card";

const COLUMNS: { key: string; label: string; color: string }[] = [
  { key: "important", label: "重要", color: "text-red-400" },
  { key: "actionable", label: "待处理", color: "text-amber-400" },
  { key: "ignorable", label: "可忽略", color: "text-gray-500" },
];

export default function InboxPage() {
  const [emails, setEmails] = useState<InboxEmail[]>([]);
  const [digest, setDigest] = useState<{ title?: string; content?: string; message?: string } | null>(null);
  const [loading, setLoading] = useState(false);
  const [polling, setPolling] = useState(false);
  const addError = useErrorStore((s) => s.addError);
  const quickChat = useQuickChat();

  const handleAiProcess = (em: InboxEmail) => {
    const prompt = `请帮我处理这封邮件：\n发件人：${em.sender}\n主题：${em.subject}\n预览：${em.preview}\n分类：${em.category}\n原因：${em.reason}`;
    quickChat({ title: `邮件：${em.subject.slice(0, 20)}`, prompt });
  };

  const load = async () => {
    setLoading(true);
    try {
      const [items, dig] = await Promise.all([
        listInboxEmails(),
        getInboxDigest(),
      ]);
      setEmails(items);
      setDigest(dig);
    } catch (err) {
      const msg =
        err instanceof ApiError ? err.message : "加载收件箱失败";
      addError(msg, "收件箱");
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    load();
  }, []);

  const handlePoll = async () => {
    setPolling(true);
    try {
      await triggerInboxPoll();
      await load();
    } catch (err) {
      const msg =
        err instanceof ApiError ? err.message : "轮询邮件失败";
      addError(msg, "收件箱");
    } finally {
      setPolling(false);
    }
  };

  const byCategory = (cat: string) => emails.filter((e) => e.category === cat);

  return (
    <div className="flex-1 overflow-y-auto p-6">
      <div className="max-w-6xl mx-auto">
        <div className="flex items-center justify-between mb-6">
          <div>
            <h2 className="text-2xl font-semibold text-gray-100">收件箱</h2>
            <p className="text-sm text-gray-500 mt-1">主动分类与每日摘要</p>
          </div>
          <Button onClick={handlePoll} disabled={polling}>
            {polling ? "轮询中..." : "立即轮询"}
          </Button>
        </div>

        {digest && digest.content && (
          <Card className="mb-6">
            <h3 className="text-sm font-medium text-emerald-400 mb-2">
              {digest.title || "今日摘要"}
            </h3>
            <pre className="text-xs text-gray-400 whitespace-pre-wrap font-sans">
              {digest.content}
            </pre>
          </Card>
        )}

        {loading && emails.length === 0 ? (
          <p className="text-gray-500 text-center py-12">加载中...</p>
        ) : (
          <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
            {COLUMNS.map((col) => (
              <Card key={col.key} padding="sm" className="p-4">
                <h3 className={`text-sm font-semibold mb-3 ${col.color}`}>
                  {col.label} ({byCategory(col.key).length})
                </h3>
                <div className="space-y-3 max-h-[60vh] overflow-y-auto">
                  {byCategory(col.key).map((em) => (
                    <div key={em.id} className="p-3 bg-gray-950 rounded-lg border border-gray-800">
                      <div className="text-sm font-medium text-gray-200 truncate">{em.subject}</div>
                      <div className="text-xs text-gray-500 mt-1 truncate">{em.sender}</div>
                      {em.reason && (
                        <div className="text-xs text-gray-600 mt-2 line-clamp-2">{em.reason}</div>
                      )}
                      <button
                        onClick={() => handleAiProcess(em)}
                        className="mt-2 text-xs text-emerald-500 hover:text-emerald-400"
                      >
                        让 AI 处理
                      </button>
                    </div>
                  ))}
                  {byCategory(col.key).length === 0 && (
                    <p className="text-xs text-gray-600 text-center py-4">暂无</p>
                  )}
                </div>
              </Card>
            ))}
          </div>
        )}
      </div>
    </div>
  );
}
