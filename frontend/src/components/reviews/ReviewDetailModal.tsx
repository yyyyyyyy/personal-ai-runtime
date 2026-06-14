import type { Review } from "../../api/types";
import { reviewPeriodLabel, reviewTypeLabel } from "../../utils/reviewUtils";
import Button from "../ui/Button";

interface Props {
  review: Review | null;
  loading?: boolean;
  error?: string | null;
  onClose: () => void;
}

function formatTime(value: string): string {
  try {
    return new Date(value).toLocaleString("zh-CN");
  } catch {
    return value;
  }
}

export default function ReviewDetailModal({ review, loading, error, onClose }: Props) {
  if (!review && !loading) return null;

  return (
    <div
      className="fixed inset-0 z-[120] flex items-center justify-center bg-black/60 p-4"
      onClick={onClose}
    >
      <div
        className="bg-gray-900 border border-gray-700 rounded-xl max-w-2xl w-full shadow-xl flex flex-col max-h-[85vh]"
        onClick={(e) => e.stopPropagation()}
      >
        <div className="px-5 pt-5 pb-3 border-b border-gray-800">
          <div className="flex items-start justify-between gap-3">
            <div className="min-w-0">
              {review ? (
                <>
                  <span className="inline-block text-xs px-2 py-0.5 rounded bg-gray-800 text-gray-400 mb-2">
                    {reviewTypeLabel(review.type)}
                  </span>
                  <h3 className="text-lg font-semibold text-gray-100">
                    {reviewPeriodLabel(review)}
                  </h3>
                  <p className="text-xs text-gray-500 mt-1">
                    {formatTime(review.created_at)}
                  </p>
                </>
              ) : (
                <h3 className="text-lg font-semibold text-gray-100">复盘详情</h3>
              )}
            </div>
            <button
              type="button"
              onClick={onClose}
              className="text-gray-500 hover:text-gray-300 text-xl leading-none shrink-0"
              aria-label="关闭"
            >
              ×
            </button>
          </div>
        </div>

        <div className="px-5 py-4 overflow-y-auto flex-1">
          {loading && (
            <p className="text-sm text-gray-500 animate-pulse">加载复盘内容…</p>
          )}
          {error && (
            <p className="text-sm text-red-400">{error}</p>
          )}
          {review && !loading && (
            <pre className="text-sm text-gray-300 whitespace-pre-wrap font-sans leading-relaxed">
              {review.content || "（无内容）"}
            </pre>
          )}
        </div>

        <div className="px-5 py-4 border-t border-gray-800 flex justify-end">
          <Button variant="secondary" size="sm" onClick={onClose}>
            关闭
          </Button>
        </div>
      </div>
    </div>
  );
}
