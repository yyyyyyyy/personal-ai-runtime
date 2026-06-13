import { toolLabel, describeToolAction } from "../../utils/toolLabels";

interface ToolCall {
  index: number;
  id: string;
  function_name: string;
  arguments: string;
}

interface Props {
  toolCall: ToolCall;
  onConfirm: () => void;
  onDeny: () => void;
}

function parseArgs(args: string): Record<string, unknown> {
  try {
    return JSON.parse(args);
  } catch {
    return {};
  }
}

export default function ConfirmationDialog({ toolCall, onConfirm, onDeny }: Props) {
  const label = toolLabel(toolCall.function_name);
  const args = parseArgs(toolCall.arguments);
  const description = describeToolAction(toolCall.function_name, args);

  return (
    <div className="bg-amber-900/30 border border-amber-600/50 rounded-lg p-4">
      <div className="flex items-start gap-3">
        <div className="text-amber-400 text-xl mt-0.5 shrink-0">⚠️</div>
        <div className="flex-1 min-w-0">
          <h4 className="text-amber-300 font-medium mb-1">
            确认{label}
          </h4>
          {description && (
            <p className="text-amber-400/60 text-sm mb-3">
              {description}
            </p>
          )}
          <details className="mb-3">
            <summary className="text-xs text-gray-500 cursor-pointer hover:text-gray-400">
              查看详细参数
            </summary>
            <pre className="bg-gray-950 p-2 mt-1 rounded text-xs text-gray-400 overflow-x-auto max-h-24 overflow-y-auto">
              {JSON.stringify(args, null, 2)}
            </pre>
          </details>
          <div className="flex gap-2">
            <button
              onClick={onConfirm}
              className="px-4 py-1.5 bg-emerald-600 hover:bg-emerald-700 rounded-lg text-sm font-medium transition-colors"
            >
              确认执行
            </button>
            <button
              onClick={onDeny}
              className="px-4 py-1.5 bg-gray-700 hover:bg-gray-600 rounded-lg text-sm transition-colors"
            >
              取消
            </button>
          </div>
        </div>
      </div>
    </div>
  );
}
