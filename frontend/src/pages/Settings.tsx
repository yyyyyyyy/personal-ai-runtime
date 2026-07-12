import { useEffect, useState } from "react";
import { useErrorStore } from "../stores/errorStore";
import { useSettingsCoreQuery, useSettingsHealthQuery } from "../hooks/useSettingsQuery";
import type { LlmSettingsResponse, EmailSettingsResponse } from "../api/client";
import Card from "../components/ui/Card";
import Button from "../components/ui/Button";
import Badge from "../components/ui/Badge";
import Spinner from "../components/ui/Spinner";
import LlmConfigCard from "../components/settings/LlmConfigCard";
import EmailConfigCard from "../components/settings/EmailConfigCard";
import DataSovereigntyCard from "../components/settings/DataSovereigntyCard";
import CapabilityTrustPanel from "../components/settings/CapabilityTrustPanel";
import PromptEditor from "../components/settings/PromptEditor";
import McpMarketplace from "../components/settings/McpMarketplace";

export default function SettingsPage() {
  const addError = useErrorStore((s) => s.addError);
  const {
    data: core,
    isLoading: coreLoading,
    error: coreError,
    refetch: refetchCore,
  } = useSettingsCoreQuery();
  const { data: health, error: healthError } = useSettingsHealthQuery();

  // Locally-cached copies of the loaded config so child cards can be re-rendered
  // with fresh data after a save without re-fetching the whole core bundle.
  const [llm, setLlm] = useState<LlmSettingsResponse | null>(null);
  const [email, setEmail] = useState<EmailSettingsResponse | null>(null);

  useEffect(() => {
    if (core) {
      setLlm(core.llm);
      setEmail(core.email);
    }
  }, [core]);

  useEffect(() => {
    if (healthError) {
      const msg = healthError instanceof Error ? healthError.message : "加载系统状态失败";
      addError(msg, "设置");
    }
  }, [healthError, addError]);

  if (coreLoading && !core) {
    return (
      <div className="flex-1 flex items-center justify-center gap-2 text-gray-500">
        <Spinner />
        加载设置…
      </div>
    );
  }

  if (!core) {
    const loadError =
      coreError instanceof Error ? coreError.message : coreError ? String(coreError) : null;
    return (
      <div className="flex-1 flex flex-col items-center justify-center gap-4 text-gray-500 p-6">
        <p>{loadError || "无法加载已保存的配置"}</p>
        <Button onClick={() => void refetchCore()}>重试</Button>
      </div>
    );
  }

  return (
    <div className="flex-1 overflow-y-auto p-6">
      <div className="max-w-3xl mx-auto space-y-6">
        <div className="flex items-center justify-between">
          <div>
            <h2 className="text-2xl font-bold text-gray-100">设置</h2>
            <p className="text-sm text-gray-500 mt-1">LLM、邮箱与数据管理</p>
          </div>
          <Badge
            tone={
              health?.status === "ok"
                ? "success"
                : health?.status === "degraded"
                  ? "warning"
                  : "danger"
            }
          >
            {health?.status === "ok"
              ? "运行正常"
              : health?.status === "degraded"
                ? "降级"
                : health?.status || "未知"}
          </Badge>
        </div>

        {llm && <LlmConfigCard llm={llm} onSaved={setLlm} />}

        {email && <EmailConfigCard email={email} onSaved={setEmail} />}

        <Card>
          <h3 className="text-sm font-medium text-gray-300 mb-3">MCP 服务器</h3>
          {!health?.startup?.checks?.mcp ? (
            <p className="text-sm text-gray-500">MCP 未启用或连接信息不可用</p>
          ) : health.startup.checks.mcp.failed > 0 ? (
            <div className="p-3 bg-amber-900/20 border border-amber-700/30 rounded-lg text-xs text-amber-300">
              MCP 服务 {health.startup.checks.mcp.connected}/{health.startup.checks.mcp.total}{" "}
              已连接，
              {health.startup.checks.mcp.failed} 个连接失败。
            </div>
          ) : (
            <p className="text-sm text-gray-400">
              全部 {health.startup.checks.mcp.total} 个 MCP 服务已连接
            </p>
          )}
        </Card>

        <Card>
          <h3 className="text-sm font-medium text-gray-300 mb-3">MCP 市场</h3>
          <p className="text-sm text-gray-500 mb-3">浏览并安装社区 MCP 服务器，扩展 AI 的能力。</p>
          <McpMarketplace />
        </Card>

        <Card>
          <h3 className="text-sm font-medium text-gray-300 mb-3">AI 能力与信任</h3>
          <p className="text-xs text-gray-500 mb-4">
            工具风险分级来自
            capability_policy.json（与运行时闸门同一来源）。需要确认的操作可在同一对话内选择信任后自动放行。
          </p>
          <CapabilityTrustPanel />
        </Card>

        <Card>
          <h3 className="text-sm font-medium text-gray-300 mb-3">系统人设</h3>
          <p className="text-sm text-gray-500 mb-3">
            自定义 AI 的身份定义和代码规则。修改后立即生效。
          </p>
          <PromptEditor />
        </Card>

        <DataSovereigntyCard onAfterImport={() => void refetchCore()} />
      </div>
    </div>
  );
}
