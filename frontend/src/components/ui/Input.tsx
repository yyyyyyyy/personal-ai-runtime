import { useCallback, useState, type InputHTMLAttributes, type TextareaHTMLAttributes } from "react";
import { Eye, EyeOff } from "lucide-react";

const DEFAULT_MASKED = "••••••••";

interface PasswordInputProps extends InputHTMLAttributes<HTMLInputElement> {
  /** True when value is a server-side masked placeholder, not the real secret. */
  isSavedSecret?: boolean;
}

interface Props extends TextareaHTMLAttributes<HTMLTextAreaElement> {
  autoGrow?: boolean;
}

export function Textarea({ autoGrow = false, className = "", onInput, ...props }: Props) {
  const handleInput = useCallback(
    (e: React.FormEvent<HTMLTextAreaElement>) => {
      if (autoGrow) {
        const el = e.currentTarget;
        el.style.height = "auto";
        el.style.height = `${Math.min(el.scrollHeight, 200)}px`;
      }
      if (onInput) {
        onInput(e as unknown as React.InputEvent<HTMLTextAreaElement>);
      }
    },
    [autoGrow, onInput]
  );

  return (
    <textarea
      className={`bg-gray-800 border border-gray-700 rounded-lg px-3 py-2 text-sm outline-none focus:border-emerald-600 text-gray-100 placeholder-gray-500 ${className}`}
      onInput={handleInput}
      {...props}
    />
  );
}

export function Input({
  className = "",
  ...props
}: React.InputHTMLAttributes<HTMLInputElement>) {
  return (
    <input
      className={`bg-gray-800 border border-gray-700 rounded-lg px-3 py-2 text-sm outline-none focus:border-emerald-600 text-gray-100 placeholder-gray-500 ${className}`}
      {...props}
    />
  );
}

export function PasswordInput({
  className = "",
  isSavedSecret = false,
  value,
  placeholder,
  type: _type,
  ...props
}: PasswordInputProps) {
  const [visible, setVisible] = useState(false);
  const masked = isSavedSecret || value === DEFAULT_MASKED || String(value ?? "").startsWith("••••");
  const showPlainSavedHint = masked && visible;
  const inputType = visible ? "text" : "password";
  const inputValue = showPlainSavedHint ? "" : value;
  const inputPlaceholder = showPlainSavedHint
    ? "密钥已保存，不可查看原文；输入新值以替换"
    : placeholder;

  return (
    <div className="relative">
      <input
        key={visible ? "visible" : "hidden"}
        type={inputType}
        value={inputValue}
        placeholder={inputPlaceholder}
        className={`w-full bg-gray-800 border border-gray-700 rounded-lg pl-3 pr-10 py-2 text-sm outline-none focus:border-emerald-600 text-gray-100 placeholder-gray-500 ${className}`}
        {...props}
      />
      <button
        type="button"
        onMouseDown={(e) => e.preventDefault()}
        onClick={() => setVisible((v) => !v)}
        className="absolute right-2 top-1/2 -translate-y-1/2 z-10 p-1.5 rounded text-gray-400 hover:text-gray-200 hover:bg-gray-700/60"
        aria-label={visible ? "隐藏密码" : "显示密码"}
        title={masked && !visible ? "已保存的密钥无法查看原文" : visible ? "隐藏" : "显示明文"}
      >
        {visible ? <EyeOff size={16} aria-hidden /> : <Eye size={16} aria-hidden />}
      </button>
    </div>
  );
}
