import type { ButtonHTMLAttributes } from "react";

type Variant = "primary" | "secondary" | "ghost" | "danger";

const variantClasses: Record<Variant, string> = {
  primary: "bg-emerald-600 hover:bg-emerald-700 text-white disabled:bg-gray-700 disabled:text-gray-500",
  secondary: "bg-gray-700 hover:bg-gray-600 text-gray-100 disabled:opacity-50",
  ghost: "bg-transparent hover:bg-gray-800 text-gray-300 disabled:opacity-50",
  danger: "bg-red-700 hover:bg-red-600 text-white disabled:opacity-50",
};

interface Props extends ButtonHTMLAttributes<HTMLButtonElement> {
  variant?: Variant;
  size?: "sm" | "md";
}

export default function Button({
  variant = "primary",
  size = "md",
  className = "",
  children,
  ...props
}: Props) {
  const sizeClass = size === "sm" ? "px-3 py-1.5 text-xs" : "px-4 py-2 text-sm";
  return (
    <button
      className={`rounded-lg font-medium transition-colors ${sizeClass} ${variantClasses[variant]} ${className}`}
      {...props}
    >
      {children}
    </button>
  );
}
