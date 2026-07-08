/**
 * QuickCaptureDialog — listens for the desktop's `quick-capture` postMessage
 * (triggered by the Alt+Shift+I global shortcut in Electron) and surfaces a
 * minimal input that saves directly to long-term memory as a quick_note.
 *
 * This closes the loop on desktop/main.js's quickCapture() — previously the
 * postMessage was sent but nothing in the renderer consumed it (dead code).
 */

import { useEffect, useRef, useState } from "react";
import { createMemory, ApiError } from "../../api/client";
import { useErrorStore } from "../../stores/errorStore";
import { Zap } from "lucide-react";

export default function QuickCaptureDialog() {
  const [open, setOpen] = useState(false);
  const [text, setText] = useState("");
  const [saving, setSaving] = useState(false);
  const [saved, setSaved] = useState(false);
  const inputRef = useRef<HTMLTextAreaElement>(null);
  const addError = useErrorStore((s) => s.addError);

  useEffect(() => {
    const handler = (e: MessageEvent) => {
      if (e.data && e.data.type === "quick-capture") {
        setOpen(true);
        setText("");
        setSaved(false);
        // Focus after the textarea renders
        setTimeout(() => inputRef.current?.focus(), 50);
      }
    };
    window.addEventListener("message", handler);
    return () => window.removeEventListener("message", handler);
  }, []);

  // Also bind a web keyboard shortcut (Ctrl/Cmd+Shift+M) for non-Electron use
  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      if ((e.ctrlKey || e.metaKey) && e.shiftKey && e.key.toLowerCase() === "m") {
        e.preventDefault();
        setOpen(true);
        setText("");
        setSaved(false);
        setTimeout(() => inputRef.current?.focus(), 50);
      }
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, []);

  const handleSave = async () => {
    const content = text.trim();
    if (!content) return;
    setSaving(true);
    try {
      await createMemory({ content, category: "quick_note" });
      setSaved(true);
      setTimeout(() => {
        setOpen(false);
        setSaved(false);
        setText("");
      }, 900);
    } catch (e) {
      addError(e instanceof ApiError ? e.message : "快速捕获失败", "记忆");
    } finally {
      setSaving(false);
    }
  };

  const handleKey = (e: React.KeyboardEvent) => {
    if (e.key === "Enter" && (e.metaKey || e.ctrlKey)) {
      e.preventDefault();
      handleSave();
    }
    if (e.key === "Escape") {
      setOpen(false);
      setText("");
    }
  };

  if (!open) return null;

  return (
    <div
      className="fixed inset-0 bg-black/40 flex items-start justify-center z-[60] pt-[20vh]"
      onClick={() => {
        setOpen(false);
        setText("");
      }}
    >
      <div
        className="bg-gray-900 border border-gray-700 rounded-xl shadow-2xl w-[28rem] max-w-[90vw] overflow-hidden"
        onClick={(e) => e.stopPropagation()}
      >
        <div className="flex items-center gap-2 px-4 py-3 border-b border-gray-800">
          <Zap size={14} className="text-amber-400" />
          <span className="text-sm font-medium text-gray-200">快速捕获</span>
          <span className="text-xs text-gray-600 ml-auto">
            {saved ? "已保存 ✓" : "⌘/Ctrl + Enter 保存"}
          </span>
        </div>
        <textarea
          ref={inputRef}
          value={text}
          onChange={(e) => setText(e.target.value)}
          onKeyDown={handleKey}
          placeholder="想到什么，立刻记下来..."
          className="w-full bg-transparent text-gray-100 text-sm px-4 py-3 outline-none resize-none h-28 placeholder:text-gray-600"
          disabled={saving || saved}
        />
        <div className="flex items-center justify-between px-4 py-2 border-t border-gray-800 bg-gray-950/50">
          <span className="text-xs text-gray-600">保存为 quick_note 记忆</span>
          <div className="flex gap-2">
            <button
              onClick={() => {
                setOpen(false);
                setText("");
              }}
              className="px-3 py-1 text-xs text-gray-400 hover:text-gray-200"
            >
              取消
            </button>
            <button
              onClick={handleSave}
              disabled={!text.trim() || saving || saved}
              className="px-3 py-1 text-xs bg-amber-600 hover:bg-amber-700 disabled:opacity-40 disabled:cursor-not-allowed rounded text-white"
            >
              {saving ? "保存中..." : saved ? "已保存" : "保存"}
            </button>
          </div>
        </div>
      </div>
    </div>
  );
}
