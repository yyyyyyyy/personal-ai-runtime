/** Strip embedded related-id prefix for notification list previews. */
export function notificationPreview(content: string): string {
  return content.replace(/^\[\[related:[^\]]+\]\]\s*/i, "");
}
