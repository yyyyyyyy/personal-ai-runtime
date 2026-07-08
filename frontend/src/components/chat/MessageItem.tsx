import { useState, useCallback } from "react";
import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";
import remarkBreaks from "remark-breaks";
import { Copy, Check, Brain, Mail, Target, FileText } from "lucide-react";
import ToolCallDisplay from "./ToolCallDisplay";
import { CodeBlock } from "./CodeBlock";
import { stripToolMarkup } from "../../utils/stripToolMarkup";
import type { SourceCitation } from "../../api/types";

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

interface DisplayMessage {
  id: string;
  role: string;
  content: string;
  isStreaming?: boolean;
  toolCalls?: ToolCall[];
  toolResults?: ToolResult[];
  expandTools?: boolean;
  created_at?: string;
  sources?: SourceCitation[];
}

interface Props {
  message: DisplayMessage;
}

function formatTimeAgo(iso?: string): string {
  if (!iso) return "";
  const diff = Date.now() - new Date(iso).getTime();
  const mins = Math.floor(diff / 60000);
  if (mins < 1) return "刚刚";
  if (mins < 60) return `${mins} 分钟前`;
  const hours = Math.floor(mins / 60);
  if (hours < 24) return `${hours} 小时前`;
  return `${Math.floor(hours / 24)} 天前`;
}

function InlineCode({ children }: { children: React.ReactNode }) {
  const [copied, setCopied] = useState(false);
  const text = String(children);

  const handleCopy = useCallback(
    (e: React.MouseEvent) => {
      e.stopPropagation();
      navigator.clipboard.writeText(text).then(() => {
        setCopied(true);
        setTimeout(() => setCopied(false), 2000);
      });
    },
    [text],
  );

  return (
    <code className="relative group bg-gray-800 px-1.5 py-0.5 rounded text-sm text-emerald-400">
      {children}
      <button
        type="button"
        onClick={handleCopy}
        className="absolute -top-1 -right-1 opacity-0 group-hover:opacity-100 bg-gray-700 hover:bg-gray-600 rounded p-0.5 transition-opacity"
        title="复制"
      >
        {copied ? (
          <Check size={10} className="text-emerald-400" />
        ) : (
          <Copy size={10} className="text-gray-400" />
        )}
      </button>
    </code>
  );
}

function SourceBadge({ source }: { source: SourceCitation }) {
  const iconMap = {
    memory: <Brain size={10} />,
    email: <Mail size={10} />,
    goal: <Target size={10} />,
    document: <FileText size={10} />,
  };
  const colorMap = {
    memory: "bg-purple-900/30 text-purple-300 border-purple-700/50",
    email: "bg-amber-900/30 text-amber-300 border-amber-700/50",
    goal: "bg-green-900/30 text-green-300 border-green-700/50",
    document: "bg-blue-900/30 text-blue-300 border-blue-700/50",
  };
  const labelMap = {
    memory: "记忆",
    email: "邮件",
    goal: "目标",
    document: "文档",
  };

  return (
    <span
      className={`inline-flex items-center gap-1 px-1.5 py-0.5 rounded text-[10px] border ${colorMap[source.type] || "bg-gray-800 text-gray-300 border-gray-600"}`}
      title={source.title}
    >
      {iconMap[source.type] || null}
      <span className="truncate max-w-[120px]">{source.title || labelMap[source.type]}</span>
    </span>
  );
}

export default function MessageItem({ message }: Props) {
  const isUser = message.role === "user";
  const isAssistant = message.role === "assistant";
  const isSystem = message.role === "system";
  const isTool = message.role === "tool";

  const displayContent = isAssistant
    ? stripToolMarkup(message.content, { trim: message.isStreaming ? false : undefined })
    : message.content;

  if (isSystem || isTool) return null;

  return (
    <div className={`flex gap-3 ${isUser ? "justify-end" : "justify-start"}`}>
      {isAssistant && (
        <div className="w-8 h-8 rounded-full bg-emerald-600/20 flex items-center justify-center shrink-0 mt-0.5">
          <span className="text-sm">🧠</span>
        </div>
      )}

      <div
        className={`max-w-[80%] rounded-2xl px-4 py-3 ${
          isUser
            ? "bg-emerald-600 text-white rounded-br-md"
            : "bg-gray-800 text-gray-100 rounded-bl-md"
        }`}
      >
        {/* Tool calls display */}
        {message.toolCalls && message.toolCalls.length > 0 && (
          <ToolCallDisplay
            toolCalls={message.toolCalls}
            toolResults={message.toolResults || []}
            defaultExpanded={message.expandTools ?? false}
          />
        )}

        {/* Message content */}
        {displayContent && (
          <div className={message.isStreaming ? "typing-cursor" : ""}>
            {isUser ? (
              <p className="whitespace-pre-wrap text-sm leading-relaxed">{displayContent}</p>
            ) : (
              <div className="markdown-content text-sm leading-relaxed prose-p:my-0">
                <ReactMarkdown
                  remarkPlugins={[remarkGfm, remarkBreaks]}
                  components={{
                    code({ className, children, ...props }) {
                      const match = /language-(\w+)/.exec(className || "");
                      const codeStr = String(children).replace(/\n$/, "");

                      if (match) {
                        const nodeProps = props as Record<string, unknown>;
                        const inline = nodeProps.inline as boolean | undefined;
                        if (inline) {
                          return <InlineCode>{children}</InlineCode>;
                        }
                        return <CodeBlock language={match[1]} code={codeStr} />;
                      }

                      if (!className && String(children).length < 50) {
                        return <InlineCode>{children}</InlineCode>;
                      }

                      return (
                        <code className={className} {...props}>
                          {children}
                        </code>
                      );
                    },
                  }}
                >
                  {displayContent}
                </ReactMarkdown>
                {message.isStreaming && (
                  <span className="inline-flex gap-0.5 ml-1 align-middle">
                    <span
                      className="w-1.5 h-1.5 bg-emerald-400 rounded-full animate-bounce"
                      style={{ animationDelay: "0ms" }}
                    />
                    <span
                      className="w-1.5 h-1.5 bg-emerald-400 rounded-full animate-bounce"
                      style={{ animationDelay: "150ms" }}
                    />
                    <span
                      className="w-1.5 h-1.5 bg-emerald-400 rounded-full animate-bounce"
                      style={{ animationDelay: "300ms" }}
                    />
                  </span>
                )}
              </div>
            )}
          </div>
        )}

        {/* Timestamp */}
        {message.created_at && (
          <div className={`text-xs mt-2 ${isUser ? "text-emerald-200/60" : "text-gray-500"}`}>
            {formatTimeAgo(message.created_at)}
          </div>
        )}

        {/* Source citations — memory + document references */}
        {isAssistant && message.sources && message.sources.length > 0 && !message.isStreaming && (
          <div className="mt-3 pt-2 border-t border-gray-700/50">
            <div className="flex items-center gap-1.5 text-xs text-purple-400 font-medium mb-2">
              <Brain size={12} />
              <span>
                {message.sources.some((s) => s.type === "document") ? "参考来源" : "我记得"}
              </span>
            </div>
            <div className="flex flex-wrap gap-1.5">
              {message.sources.map((source, idx) => (
                <SourceBadge key={`${source.id}-${idx}`} source={source} />
              ))}
            </div>
          </div>
        )}
      </div>

      {isUser && (
        <div className="w-8 h-8 rounded-full bg-emerald-600 flex items-center justify-center shrink-0 mt-0.5">
          <span className="text-sm text-white font-medium">你</span>
        </div>
      )}
    </div>
  );
}
