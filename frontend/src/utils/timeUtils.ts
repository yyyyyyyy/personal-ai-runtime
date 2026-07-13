export function timeAgo(dateStr: string): string {
  const diff = Date.now() - new Date(dateStr).getTime();
  const mins = Math.floor(diff / 60000);
  if (mins < 1) return "刚刚";
  if (mins < 60) return `${mins} 分钟前`;
  const hours = Math.floor(mins / 60);
  if (hours < 24) return `${hours} 小时前`;
  const days = Math.floor(hours / 24);
  if (days < 7) return `${days} 天前`;
  return new Date(dateStr).toLocaleDateString("zh-CN");
}

/**
 * Compact relative-time formatter: shows "天前/小时前/分钟前/刚刚", and
 * falls back to a month/day locale date once older than 30 days. Used in
 * dense UIs (memory list, provenance timeline) where space is tight.
 */
export function timeAgoShort(dateStr: string): string {
  const d = new Date(dateStr);
  const diff = Date.now() - d.getTime();
  const days = Math.floor(diff / 86400000);
  if (days > 30) return d.toLocaleDateString("zh-CN", { month: "short", day: "numeric" });
  if (days > 0) return `${days} 天前`;
  const hours = Math.floor(diff / 3600000);
  if (hours > 0) return `${hours} 小时前`;
  const mins = Math.floor(diff / 60000);
  if (mins > 0) return `${mins} 分钟前`;
  return "刚刚";
}

export function isStagnant(
  lastActivity: string | null,
  createdAt?: string,
  days: number = 3,
): boolean {
  const referenceTime = lastActivity || createdAt;
  if (!referenceTime) return false;
  return Date.now() - new Date(referenceTime).getTime() > days * 86400000;
}
