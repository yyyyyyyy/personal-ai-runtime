import { describe, expect, it } from "vitest";
import {
  findReviewForNotification,
  notificationPreview,
  parseRelatedId,
} from "./reviewUtils";
import type { Review } from "../api/types";

describe("reviewUtils", () => {
  it("parseRelatedId extracts embedded review id", () => {
    const result = parseRelatedId("@related:abc-123\n预览内容");
    expect(result.relatedId).toBe("abc-123");
    expect(result.body).toBe("预览内容");
  });

  it("notificationPreview strips related id prefix", () => {
    expect(notificationPreview("@related:x\nhello")).toBe("hello");
  });

  it("findReviewForNotification matches daily title", () => {
    const reviews: Review[] = [
      {
        id: "d1",
        type: "daily",
        period_start: "2026-06-14",
        period_end: "2026-06-14",
        content: "daily",
        created_at: "2026-06-14T00:00:00Z",
      },
    ];
    const found = findReviewForNotification("每日复盘 - 2026-06-14", reviews);
    expect(found?.id).toBe("d1");
  });
});
