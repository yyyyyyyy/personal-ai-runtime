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

function formatArgs(args: string): string {
  try {
    return JSON.stringify(JSON.parse(args), null, 2);
  } catch {
    return args;
  }
}

export default function ConfirmationDialog({ toolCall, onConfirm, onDeny }: Props) {
  return (
    <div className="bg-amber-900/30 border border-amber-600/50 rounded-lg p-4 mb-3">
      <div className="flex items-start gap-3">
        <div className="text-amber-400 text-xl mt-0.5 shrink-0">⚠️</div>
        <div className="flex-1 min-w-0">
          <h4 className="text-amber-300 font-medium mb-2">
            确认操作: {toolCall.function_name}
          </h4>
          <pre className="bg-gray-950 p-2 rounded text-xs text-gray-300 overflow-x-auto max-h-32 overflow-y-auto mb-3">
            {formatArgs(toolCall.arguments)}
          </pre>
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
