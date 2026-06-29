import type { HTMLAttributes } from "react";

interface Props extends HTMLAttributes<HTMLDivElement> {
  padding?: "sm" | "md";
}

export default function Card({
  padding = "md",
  className = "",
  children,
  ...props
}: Props) {
  const pad = padding === "sm" ? "p-3" : "p-4";
  return (
    <div
      className={`bg-gray-900 border border-gray-800 rounded-xl ${pad} ${className}`}
      {...props}
    >
      {children}
    </div>
  );
}
