import type { Review } from "../api/types";

/** Parse @related:uuid prefix embedded in notification content. */
export function parseRelatedId(content: string): { relatedId: string | null; body: string } {
  if (content.startsWith("@related:")) {
    const firstLineEnd = content.indexOf("\n");
    if (firstLineEnd === -1) {
      return { relatedId: content.slice("@related:".length), body: "" };
    }
    return {
      relatedId: content.slice("@related:".length, firstLineEnd),
      body: content.slice(firstLineEnd + 1),
    };
  }
  return { relatedId: null, body: content };
}

export function reviewTypeLabel(type: string): string {
  if (type === "daily") return "每日复盘";
  if (type === "weekly") return "每周复盘";
  if (type === "monthly") return "每月复盘";
  return type;
}

export function reviewPeriodLabel(review: Review): string {
  if (review.period_end !== review.period_start) {
    return `${review.period_start} ~ ${review.period_end}`;
  }
  return review.period_start;
}

export function findReviewForNotification(title: string, reviews: Review[]): Review | undefined {
  const dailyMatch = title.match(/^每日复盘 - (\d{4}-\d{2}-\d{2})$/);
  if (dailyMatch) {
    return reviews.find((r) => r.type === "daily" && r.period_start === dailyMatch[1]);
  }

  const weeklyMatch = title.match(/^每周复盘 - (.+?) ~ (.+)$/);
  if (weeklyMatch) {
    return reviews.find(
      (r) =>
        r.type === "weekly" &&
        r.period_start === weeklyMatch[1] &&
        r.period_end === weeklyMatch[2],
    );
  }

  const monthlyMatch = title.match(/^每月复盘 - (.+?) ~ (.+)$/);
  if (monthlyMatch) {
    return reviews.find(
      (r) =>
        r.type === "monthly" &&
        r.period_start === monthlyMatch[1] &&
        r.period_end === monthlyMatch[2],
    );
  }

  return undefined;
}

/** Strip embedded related id prefix for notification list previews. */
export function notificationPreview(content: string): string {
  return parseRelatedId(content).body;
}
