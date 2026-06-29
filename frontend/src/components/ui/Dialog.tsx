import Button from "./Button";

interface Props {
  open: boolean;
  title: string;
  description?: string;
  confirmLabel?: string;
  cancelLabel?: string;
  variant?: "danger" | "primary";
  onConfirm: () => void;
  onCancel: () => void;
}

export default function Dialog({
  open,
  title,
  description,
  confirmLabel = "确认",
  cancelLabel = "取消",
  variant = "primary",
  onConfirm,
  onCancel,
}: Props) {
  if (!open) return null;

  return (
    <div className="fixed inset-0 z-[100] flex items-center justify-center bg-black/60">
      <div className="bg-gray-900 border border-gray-700 rounded-xl p-6 max-w-md w-full mx-4 shadow-xl">
        <h3 className="text-lg font-semibold text-gray-100">{title}</h3>
        {description && (
          <p className="text-sm text-gray-400 mt-2">{description}</p>
        )}
        <div className="flex justify-end gap-2 mt-6">
          <Button variant="secondary" size="sm" onClick={onCancel}>
            {cancelLabel}
          </Button>
          <Button
            variant={variant === "danger" ? "danger" : "primary"}
            size="sm"
            onClick={onConfirm}
          >
            {confirmLabel}
          </Button>
        </div>
      </div>
    </div>
  );
}
