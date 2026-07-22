import { describe, expect, it, vi } from "vitest";
import { applyWsInvalidation, queryKeys } from "./useWsInvalidationBridge";

function makeQc() {
  return {
    invalidateQueries: vi.fn(),
  };
}

describe("applyWsInvalidation", () => {
  it("invalidates memory-related keys on memory_changed", () => {
    const qc = makeQc();
    applyWsInvalidation(qc as never, { type: "memory_changed" });
    const keys = qc.invalidateQueries.mock.calls.map((c) => c[0].queryKey);
    expect(keys).toEqual(
      expect.arrayContaining([
        queryKeys.memories,
        queryKeys.dashboard,
        queryKeys.portrait,
        queryKeys.trustReport,
        queryKeys.timeline,
      ]),
    );
  });

  it("invalidates approvals on approval_changed", () => {
    const qc = makeQc();
    applyWsInvalidation(qc as never, { type: "approval_changed", approval_id: "a1" });
    const keys = qc.invalidateQueries.mock.calls.map((c) => c[0].queryKey);
    expect(keys).toEqual(
      expect.arrayContaining([queryKeys.approvals, queryKeys.trustReport, queryKeys.dashboard]),
    );
  });

  it("invalidates goals on goal_changed", () => {
    const qc = makeQc();
    applyWsInvalidation(qc as never, { type: "goal_changed", work_item_id: "g1" });
    const keys = qc.invalidateQueries.mock.calls.map((c) => c[0].queryKey);
    expect(keys).toEqual(
      expect.arrayContaining([
        queryKeys.goals,
        queryKeys.dashboard,
        queryKeys.timeline,
        queryKeys.trustReport,
        queryKeys.portrait,
      ]),
    );
  });

  it("routes notification_type to inbox/goals", () => {
    const qc = makeQc();
    applyWsInvalidation(qc as never, {
      type: "notification",
      notification_type: "inbox_digest",
    });
    let keys = qc.invalidateQueries.mock.calls.map((c) => c[0].queryKey);
    expect(keys).toEqual(
      expect.arrayContaining([queryKeys.notifications, queryKeys.inbox, queryKeys.dashboard]),
    );

    qc.invalidateQueries.mockClear();
    applyWsInvalidation(qc as never, {
      type: "notification",
      notification_type: "goal_stagnant",
    });
    keys = qc.invalidateQueries.mock.calls.map((c) => c[0].queryKey);
    expect(keys).toEqual(
      expect.arrayContaining([queryKeys.notifications, queryKeys.goals, queryKeys.dashboard]),
    );
  });

  it("ignores unknown event types", () => {
    const qc = makeQc();
    applyWsInvalidation(qc as never, { type: "pong" });
    expect(qc.invalidateQueries).not.toHaveBeenCalled();
  });
});
