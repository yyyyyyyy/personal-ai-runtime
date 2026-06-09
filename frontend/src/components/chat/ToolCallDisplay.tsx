import { useState } from "react";

interface ToolCall {
  index: number;
  id: string;
  function_name: string;
  arguments: string;
}

interface ToolResult {
  tool_name: string;
  tool_call_id: string;
  content: string;
}

interface Props {
  toolCalls: ToolCall[];
  toolResults: ToolResult[];
}

function formatArgs(args: string): string {
  try {
    const parsed = JSON.parse(args);
    return JSON.stringify(parsed, null, 2);
  } catch {
    return args;
  }
}

function formatResult(content: string): string {
  try {
    const parsed = JSON.parse(content);
    return JSON.stringify(parsed, null, 2);
  } catch {
    if (content.length > 500) {
      return content.slice(0, 500) + "\n... [truncated]";
    }
    return content;
  }
}

function getToolIcon(name: string): string {
  const icons: Record<string, string> = {
    get_current_time: "🕐",
    read_file: "📄",
    list_directory: "📁",
    write_file: "✍️",
    web_search: "🔍",
    fetch_url: "🌐",
  };
  return icons[name] || "🔧";
}

export default function ToolCallDisplay({ toolCalls, toolResults }: Props) {
  const [expandedCall, setExpandedCall] = useState<number | null>(null);

  const getResult = (toolName: string, callId: string) => {
    return toolResults.find(
      (r) => r.tool_name === toolName || r.tool_call_id === callId
    );
  };

  if (toolCalls.length === 0) return null;

  return (
    <div className="mb-3 space-y-2">
      {toolCalls.map((tc, idx) => {
        const result = getResult(tc.function_name, tc.id);
        const isExpanded = expandedCall === idx;

        return (
          <div
            key={tc.id || idx}
            className="bg-gray-900/60 rounded-lg border border-gray-700 overflow-hidden"
          >
            <button
              onClick={() => setExpandedCall(isExpanded ? null : idx)}
              className="w-full flex items-center gap-2 px-3 py-2 text-xs text-gray-400 hover:text-gray-200 transition-colors"
            >
              <span>{getToolIcon(tc.function_name)}</span>
              <span className="text-emerald-400 font-medium">
                {tc.function_name}
              </span>
              {result ? (
                <span className="ml-auto text-emerald-500">✓ 完成</span>
              ) : (
                <span className="ml-auto flex items-center gap-1">
                  <svg className="animate-spin h-3 w-3" viewBox="0 0 24 24">
                    <circle
                      className="opacity-25"
                      cx="12" cy="12" r="10"
                      stroke="currentColor" strokeWidth="4" fill="none"
                    />
                    <path
                      className="opacity-75"
                      fill="currentColor"
                      d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4z"
                    />
                  </svg>
                  执行中
                </span>
              )}
              <svg
                className={`w-3 h-3 transition-transform ${isExpanded ? "rotate-180" : ""}`}
                fill="none" stroke="currentColor" viewBox="0 0 24 24"
              >
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M19 9l-7 7-7-7" />
              </svg>
            </button>

            {isExpanded && (
              <div className="border-t border-gray-700 px-3 py-2 space-y-2 text-xs">
                <div>
                  <div className="text-gray-500 mb-1">参数</div>
                  <pre className="bg-gray-950 p-2 rounded text-gray-300 overflow-x-auto">
                    {formatArgs(tc.arguments)}
                  </pre>
                </div>
                {result && (
                  <div>
                    <div className="text-gray-500 mb-1">结果</div>
                    <pre className="bg-gray-950 p-2 rounded text-gray-300 overflow-x-auto max-h-48 overflow-y-auto">
                      {formatResult(result.content)}
                    </pre>
                  </div>
                )}
              </div>
            )}
          </div>
        );
      })}
    </div>
  );
}
