import { useEffect, useState } from "react";
import ProjectionBadge from "../components/ProjectionBadge";
import { useAppStore } from "../stores/appStore";
import {
  listMemoriesGrouped,
  listPendingTrajectoryLinks,
  ratifyClaim,
  rejectClaim,
  type MemoryRow,
} from "../api/client";

function ClaimStatusBadge({ status }: { status?: string | null }) {
  const map: Record<string, string> = {
    proposed: "bg-amber-900/40 text-amber-300",
    ratified: "bg-emerald-900/40 text-emerald-300",
    contested: "bg-orange-900/40 text-orange-300",
    rejected: "bg-gray-800 text-gray-500",
    released: "bg-gray-800 text-gray-500",
  };
  const label = status || "proposed";
  return (
    <span className={`text-xs px-2 py-0.5 rounded ${map[label] || map.proposed}`}>
      {label}
    </span>
  );
}

export default function MemoriesPage() {
  const setPage = useAppStore((s) => s.setPage);
  const experimentalTrajectoryEnabled = useAppStore(
    (s) => s.experimentalTrajectoryEnabled
  );
  const [selfReports, setSelfReports] = useState<MemoryRow[]>([]);
  const [claims, setClaims] = useState<MemoryRow[]>([]);
  const [pendingCount, setPendingCount] = useState(0);
  const [note, setNote] = useState("");
  const [loading, setLoading] = useState(true);

  const load = async () => {
    setLoading(true);
    try {
      const grouped = await listMemoriesGrouped();
      setSelfReports(grouped.self_reports);
      setClaims(grouped.claims);
      setNote(grouped.projection_note);
      if (experimentalTrajectoryEnabled) {
        const pending = await listPendingTrajectoryLinks();
        setPendingCount(pending.pending.length);
      } else {
        setPendingCount(0);
      }
    } catch {
      // backend offline
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    load();
  }, [experimentalTrajectoryEnabled]);

  const onRatify = async (id: string) => {
    await ratifyClaim(id);
    await load();
  };

  const onReject = async (id: string) => {
    await rejectClaim(id);
    await load();
  };

  if (loading) {
    return (
      <div className="flex-1 flex items-center justify-center text-gray-500">加载中…</div>
    );
  }

  return (
    <div className="flex-1 overflow-y-auto p-6">
      <div className="max-w-3xl mx-auto space-y-8">
        <div>
          <h2 className="text-2xl font-bold mb-2">记忆与解释</h2>
          <p className="text-sm text-gray-500">{note}</p>
          <div className="mt-2">
            <ProjectionBadge
              parsed={{
                projection: true,
                not_ratified: true,
                interpretive_plurality: true,
              }}
            />
          </div>
        </div>

        <section>
          <h3 className="text-sm font-semibold text-emerald-400 mb-3">你的自述（Self-Report）</h3>
          {selfReports.length === 0 ? (
            <p className="text-gray-600 text-sm">暂无用户自述记忆。</p>
          ) : (
            <ul className="space-y-2">
              {selfReports.map((m) => (
                <li key={m.id} className="bg-gray-900 border border-gray-800 rounded-lg p-3 text-sm">
                  {m.content}
                </li>
              ))}
            </ul>
          )}
        </section>

        <section>
          <h3 className="text-sm font-semibold text-amber-400 mb-3">系统推断（Claim · 可署名）</h3>
          {claims.length === 0 ? (
            <p className="text-gray-600 text-sm">暂无系统推断。</p>
          ) : (
            <ul className="space-y-3">
              {claims.map((m) => (
                <li key={m.id} className="bg-gray-900 border border-gray-800 rounded-lg p-3">
                  <div className="flex items-start justify-between gap-2 mb-2">
                    <p className="text-sm text-gray-300 flex-1">{m.content}</p>
                    <ClaimStatusBadge status={m.claim_status} />
                  </div>
                  {m.claim_status === "proposed" && (
                    <div className="flex gap-2">
                      <button
                        type="button"
                        onClick={() => onRatify(m.id)}
                        className="text-xs px-3 py-1 rounded bg-emerald-700 hover:bg-emerald-600"
                      >
                        署名
                      </button>
                      <button
                        type="button"
                        onClick={() => onReject(m.id)}
                        className="text-xs px-3 py-1 rounded bg-gray-700 hover:bg-gray-600"
                      >
                        拒绝
                      </button>
                    </div>
                  )}
                </li>
              ))}
            </ul>
          )}
        </section>

        {experimentalTrajectoryEnabled && (
          <section className="bg-gray-900/40 border border-gray-800 rounded-lg p-4">
            <h3 className="text-sm font-semibold text-indigo-400 mb-2">轨迹链接</h3>
            <p className="text-xs text-gray-500 mb-3">
              连续性解释在「轨迹」页管理。
              {pendingCount > 0 && ` 当前有 ${pendingCount} 条待确认链接。`}
            </p>
            <button
              type="button"
              onClick={() => setPage("trajectories")}
              className="text-xs px-3 py-1.5 rounded bg-indigo-800 hover:bg-indigo-700"
            >
              打开轨迹页 →
            </button>
          </section>
        )}
      </div>
    </div>
  );
}
