import { useEffect, useState } from "react";
import ProjectionBadge from "../components/ProjectionBadge";
import {
  getTrajectory,
  listPendingTrajectoryLinks,
  listTrajectories,
  optInTrajectoryIdentity,
  optOutTrajectoryIdentity,
  ratifyTrajectoryLink,
  rejectTrajectoryLink,
  type TrajectoryPendingLink,
  type TrajectorySummary,
} from "../api/client";

function LinkStatusBadge({ status }: { status?: string }) {
  const map: Record<string, string> = {
    proposed: "bg-amber-900/40 text-amber-300",
    ratified: "bg-emerald-900/40 text-emerald-300",
    rejected: "bg-gray-800 text-gray-500",
    released: "bg-gray-800 text-gray-500 line-through",
    contested: "bg-orange-900/40 text-orange-300",
  };
  const label = status || "proposed";
  return (
    <span className={`text-xs px-2 py-0.5 rounded ${map[label] || map.proposed}`}>
      {label}
    </span>
  );
}

export default function TrajectoriesPage() {
  const [trajectories, setTrajectories] = useState<TrajectorySummary[]>([]);
  const [pendingLinks, setPendingLinks] = useState<TrajectoryPendingLink[]>([]);
  const [selectedId, setSelectedId] = useState<string | null>(null);
  const [linkCounts, setLinkCounts] = useState<Record<string, number>>({});
  const [loading, setLoading] = useState(true);

  const load = async () => {
    setLoading(true);
    try {
      const [trajRes, pendingRes] = await Promise.all([
        listTrajectories(),
        listPendingTrajectoryLinks(),
      ]);
      setTrajectories(trajRes.trajectories);
      setPendingLinks(pendingRes.pending);

      const counts: Record<string, number> = {};
      await Promise.all(
        trajRes.trajectories.map(async (t) => {
          if (!t.id) return;
          try {
            const detail = await getTrajectory(t.id);
            counts[t.id] = detail.links?.length ?? 0;
          } catch {
            counts[t.id] = 0;
          }
        })
      );
      setLinkCounts(counts);
    } catch {
      // backend offline
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    load();
  }, []);

  const onRatifyLink = async (linkId: string) => {
    await ratifyTrajectoryLink(linkId);
    await load();
  };

  const onRejectLink = async (linkId: string) => {
    await rejectTrajectoryLink(linkId);
    await load();
  };

  const onOptInIdentity = async (trajectoryId: string) => {
    await optInTrajectoryIdentity(trajectoryId);
    await load();
  };

  const onOptOutIdentity = async (trajectoryId: string) => {
    await optOutTrajectoryIdentity(trajectoryId);
    await load();
  };

  const selected = trajectories.find((t) => t.id === selectedId);

  if (loading) {
    return (
      <div className="flex-1 flex items-center justify-center text-gray-500">加载中…</div>
    );
  }

  return (
    <div className="flex-1 overflow-y-auto p-6">
      <div className="max-w-4xl mx-auto space-y-8">
        <div>
          <h2 className="text-2xl font-bold mb-2">轨迹（连续性解释）</h2>
          <p className="text-sm text-gray-500">
            轨迹是对事件连续性的假说，不是事实。竞争解释可能并存；确认链接仅表示你认可该关联，不等于身份认定。
          </p>
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
          <h3 className="text-sm font-semibold text-amber-400 mb-3">
            待确认链接
            {pendingLinks.length > 0 && (
              <span className="ml-2 text-xs bg-amber-900/50 text-amber-200 px-2 py-0.5 rounded-full">
                {pendingLinks.length}
              </span>
            )}
          </h3>
          {pendingLinks.length === 0 ? (
            <p className="text-gray-600 text-sm">暂无待确认的轨迹链接。</p>
          ) : (
            <ul className="space-y-3">
              {pendingLinks.map((lnk) => (
                <li
                  key={lnk.link_id}
                  className="bg-gray-900 border border-amber-900/40 rounded-lg p-4 text-sm"
                >
                  <div className="flex items-center justify-between gap-2 mb-2">
                    <span className="text-indigo-300 font-medium">{lnk.trajectory_id}</span>
                    <LinkStatusBadge status={lnk.claim_status} />
                  </div>
                  <div className="text-gray-500 text-xs mb-2">
                    事件 seq={lnk.event_seq}
                    {lnk.confidence != null && ` · 置信度 ${(lnk.confidence * 100).toFixed(0)}%`}
                  </div>
                  <p className="text-gray-300 mb-3">
                    {lnk.rationale || "系统提议：此事件可能属于该连续性解释"}
                  </p>
                  {lnk.trajectory?.competing_with && lnk.trajectory.competing_with.length > 0 && (
                    <p className="text-xs text-gray-500 mb-3">
                      竞争轨迹: {lnk.trajectory.competing_with.join(", ")}
                    </p>
                  )}
                  <div className="flex gap-2">
                    <button
                      type="button"
                      onClick={() => onRatifyLink(lnk.link_id)}
                      className="text-xs px-3 py-1.5 rounded bg-indigo-700 hover:bg-indigo-600"
                    >
                      确认链接
                    </button>
                    <button
                      type="button"
                      onClick={() => onRejectLink(lnk.link_id)}
                      className="text-xs px-3 py-1.5 rounded bg-gray-700 hover:bg-gray-600"
                    >
                      拒绝
                    </button>
                  </div>
                </li>
              ))}
            </ul>
          )}
        </section>

        <section>
          <h3 className="text-sm font-semibold text-indigo-400 mb-3">注册轨迹</h3>
          {trajectories.length === 0 ? (
            <p className="text-gray-600 text-sm">暂无轨迹注册表条目。</p>
          ) : (
            <div className="grid gap-3 sm:grid-cols-2">
              {trajectories.map((t) => {
                const isReleased =
                  t.status === "released" || t.claim_status === "released";
                return (
                <button
                  key={t.id}
                  type="button"
                  onClick={() => setSelectedId(selectedId === t.id ? null : t.id!)}
                  className={`text-left bg-gray-900 border rounded-lg p-4 transition-colors ${
                    isReleased ? "opacity-70 border-gray-800" : ""
                  } ${
                    selectedId === t.id
                      ? "border-indigo-600 ring-1 ring-indigo-600/30"
                      : "border-gray-800 hover:border-gray-700"
                  }`}
                >
                  <div className="text-sm font-medium text-gray-200 mb-1 flex items-center gap-2">
                    <span>{t.id}</span>
                    {isReleased && (
                      <span className="text-xs px-2 py-0.5 rounded bg-gray-800 text-gray-500 border border-gray-700">
                        已放下
                      </span>
                    )}
                  </div>
                  <p className="text-xs text-gray-500 mb-2 line-clamp-2">{t.description}</p>
                  <div className="flex flex-wrap gap-2 text-xs">
                    {t.domain && (
                      <span className="px-2 py-0.5 rounded bg-gray-800 text-gray-400">{t.domain}</span>
                    )}
                    <span className="text-gray-600">
                      {linkCounts[t.id!] ?? 0} 条链接
                    </span>
                    <span
                      className={
                        t.identity_narrative_opt_in
                          ? "text-emerald-400"
                          : "text-gray-500"
                      }
                    >
                      {t.identity_narrative_opt_in ? "已授权身份叙事" : "未授权身份叙事"}
                    </span>
                  </div>
                  {t.competing_with && t.competing_with.length > 0 && (
                    <p className="text-xs text-amber-600/80 mt-2">
                      竞争: {t.competing_with.join(", ")}
                    </p>
                  )}
                </button>
              );
              })}
            </div>
          )}
        </section>

        {selected && (
          <section className="bg-gray-900/50 border border-gray-800 rounded-lg p-4">
            <h4 className="text-sm font-semibold text-gray-300 mb-2">{selected.id} 详情</h4>
            <p className="text-sm text-gray-400">{selected.description}</p>
            {selected.competing_with && selected.competing_with.length > 0 && (
              <p className="text-xs text-gray-500 mt-2">
                与之竞争的解释: {selected.competing_with.join(" · ")}
              </p>
            )}
            <p className="text-xs text-gray-500 mt-3">
              身份叙事授权（Identity RFC P4）：默认关闭；开启后该轨迹可参与「我是谁」类投影编织。
            </p>
            <div className="flex gap-2 mt-2">
              {selected.identity_narrative_opt_in ? (
                <button
                  type="button"
                  onClick={() => onOptOutIdentity(selected.id!)}
                  className="text-xs px-3 py-1.5 rounded bg-gray-700 hover:bg-gray-600"
                >
                  撤销身份叙事授权
                </button>
              ) : (
                <button
                  type="button"
                  onClick={() => onOptInIdentity(selected.id!)}
                  className="text-xs px-3 py-1.5 rounded bg-emerald-800 hover:bg-emerald-700"
                >
                  授权参与身份叙事
                </button>
              )}
            </div>
          </section>
        )}
      </div>
    </div>
  );
}
