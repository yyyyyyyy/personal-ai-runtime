interface Props {
  icon?: React.ReactNode;
  title: string;
  description?: string;
  action?: React.ReactNode;
}

export default function EmptyState({ icon, title, description, action }: Props) {
  return (
    <div className="flex flex-col items-center justify-center py-12 text-center">
      {icon && <div className="text-4xl mb-4 opacity-60">{icon}</div>}
      <h3 className="text-lg font-medium text-gray-300">{title}</h3>
      {description && (
        <p className="text-sm text-gray-500 mt-2 max-w-sm">{description}</p>
      )}
      {action && <div className="mt-6">{action}</div>}
    </div>
  );
}
