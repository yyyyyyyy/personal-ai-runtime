/** Map notification type to in-app route. */
export function notificationTargetPath(type: string): string | null {
  if (type === "goal_stagnant" || type.includes("goal")) return "/goals";
  if (type.includes("brief") || type.includes("review")) return "/dashboard";
  if (type.includes("inbox") || type.includes("email")) return "/inbox";
  if (type === "suggestion") return "/dashboard";
  return "/dashboard";
}

export function notificationTypeLabel(type: string): string {
  if (type.includes("inbox_digest")) return "收件箱摘要";
  if (type.includes("inbox") || type.includes("email")) return "邮件";
  if (type.includes("brief")) return "晨报";
  if (type.includes("review")) return "回顾";
  if (type.includes("goal")) return "目标";
  if (type === "suggestion") return "主动建议";
  return type;
}
