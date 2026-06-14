import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";
import ToolCallDisplay from "./ToolCallDisplay";
import { CodeBlock } from "./CodeBlock";
import { stripToolMarkup } from "../../utils/stripToolMarkup";

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
}

interface Props {
  message: DisplayMessage;
}

export default function MessageItem({ message }: Props) {
  const isUser = message.role === "user";
  const isAssistant = message.role === "assistant";
  const isSystem = message.role === "system";
  const isTool = message.role === "tool";

  // Defensive strip: ensure no tool markup leaks into the rendered content
  const displayContent = isAssistant ? stripToolMarkup(message.content) : message.content;

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
              <p className="whitespace-pre-wrap text-sm leading-relaxed">
                {displayContent}
              </p>
            ) : (
              <div className="markdown-content text-sm leading-relaxed prose-p:my-0">
                <ReactMarkdown
                  remarkPlugins={[remarkGfm]}
                  components={{
                    code({ className, children, ...props }) {
                      const match = /language-(\w+)/.exec(className || "");
                      const codeStr = String(children).replace(/\n$/, "");

                      if (match) {
                        const nodeProps = props as Record<string, unknown>;
                        const inline = nodeProps.inline as boolean | undefined;
                        if (inline) {
                          return (
                            <code className={className} {...props}>
                              {children}
                            </code>
                          );
                        }
                        return (
                          <CodeBlock language={match[1]} code={codeStr} />
                        );
                      }

                      if (!className && String(children).length < 50) {
                        return (
                          <code className="bg-gray-800 px-1.5 py-0.5 rounded text-sm text-emerald-400">
                            {children}
                          </code>
                        );
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
              </div>
            )}
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
