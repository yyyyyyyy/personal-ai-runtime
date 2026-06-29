type Tone = "default" | "success" | "warning" | "danger" | "info";

const toneClasses: Record<Tone, string> = {
  default: "bg-gray-700 text-gray-300",
  success: "bg-emerald-900/50 text-emerald-400",
  warning: "bg-amber-900/50 text-amber-400",
  danger: "bg-red-900/50 text-red-400",
  info: "bg-blue-900/50 text-blue-400",
};

interface Props {
  children: React.ReactNode;
  tone?: Tone;
  className?: string;
}

export default function Badge({ children, tone = "default", className = "" }: Props) {
  return (
    <span
      className={`inline-flex items-center text-xs px-2 py-0.5 rounded-full ${toneClasses[tone]} ${className}`}
    >
      {children}
    </span>
  );
}
