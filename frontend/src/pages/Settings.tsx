import { useCallback, useEffect, useState } from "react";
import {
  getSystemHealth,
  fetchSystemInfo,
  getMcpStatus,
  exportData,
  importData,
  getLlmSettings,
  updateLlmSettings,
  testLlmConnection,
  getEmailSettings,
  updateEmailSettings,
  testEmailConnection,
  ApiError,
  type HealthResponse,
  type SystemInfo,
  type McpStatusResponse,
  type LlmSettingsResponse,
  type LlmProviderConfig,
  type EmailSettingsResponse,
} from "../api/client";
import { useErrorStore } from "../stores/errorStore";
import Card from "../components/ui/Card";
import Button from "../components/ui/Button";
import Badge from "../components/ui/Badge";
import { Input, PasswordInput } from "../components/ui/Input";
import Spinner from "../components/ui/Spinner";

const STATUS_LABELS: Record<string, string> = {
  connected: "已连接",
  lazy: "懒加载",
  disconnected: "未连接",
  unavailable: "不可用",
};

const STATUS_TONE: Record<string, "success" | "warning" | "danger" | "default"> = {
  connected: "success",
  lazy: "warning",
  disconnected: "default",
  unavailable: "danger",
};

const MASKED_SECRET = "••••••••";

function emptyProvider(id = ""): LlmProviderConfig {
  return {
    id,
    name: "",
    type: "openai_compatible",
    base_url: "",
    model: "",
    api_key: "",
    enabled: true,
  };
}

export default function SettingsPage() {
  const addError = useErrorStore((s) => s.addError);
  const [health, setHealth] = useState<HealthResponse | null>(null);
  const [info, setInfo] = useState<SystemInfo | null>(null);
  const [llmSettings, setLlmSettings] = useState<LlmSettingsResponse | null>(null);
  const [llmForm, setLlmForm] = useState<LlmProviderConfig[]>([]);
  const [llmDefault, setLlmDefault] = useState("deepseek");
  const [llmTemperature, setLlmTemperature] = useState(0.7);
  const [llmMaxTokens, setLlmMaxTokens] = useState(4096);
  const [emailSettings, setEmailSettings] = useState<EmailSettingsResponse | null>(null);
  const [emailUser, setEmailUser] = useState("");
  const [emailPass, setEmailPass] = useState("");
  const [mcp, setMcp] = useState<McpStatusResponse | null>(null);
  const [loading, setLoading] = useState(true);
  const [settingsReady, setSettingsReady] = useState(false);
  const [loadError, setLoadError] = useState<string | null>(null);
  const [exporting, setExporting] = useState(false);
  const [importing, setImporting] = useState(false);
  const [importConfirm, setImportConfirm] = useState("");
  const [savingLlm, setSavingLlm] = useState(false);
  const [savingEmail, setSavingEmail] = useState(false);
  const [testingLlm, setTestingLlm] = useState<string | null>(null);
  const [testingEmail, setTestingEmail] = useState(false);
  const [emailTestResult, setEmailTestResult] = useState<{
    ok: boolean;
    imap_ok: boolean;
    smtp_ok: boolean;
    error?: string | null;
  } | null>(null);

  const applyLlmSettings = (llm: LlmSettingsResponse) => {
    setLlmSettings(llm);
    setLlmForm(llm.config.providers.map((p) => ({ ...p })));
    setLlmDefault(llm.config.default_provider);
    setLlmTemperature(llm.config.temperature);
    setLlmMaxTokens(llm.config.max_tokens);
  };

  const applyEmailSettings = (email: EmailSettingsResponse) => {
    setEmailSettings(email);
    setEmailUser(email.config.user);
    setEmailPass(email.config.password);
    setEmailTestResult(null);
  };

  const load = useCallback(async () => {
    setLoading(true);
    setLoadError(null);
    setSettingsReady(false);
    try {
      const [llm, email] = await Promise.all([getLlmSettings(), getEmailSettings()]);
      applyLlmSettings(llm);
      applyEmailSettings(email);
      setSettingsReady(true);
    } catch (err) {
      const msg = err instanceof ApiError ? err.message : "加载 LLM/邮箱配置失败";
      setLoadError(msg);
      addError(msg, "设置");
    }

    try {
      const [h, i, m] = await Promise.all([
        getSystemHealth(),
        fetchSystemInfo(),
        getMcpStatus(),
      ]);
      setHealth(h);
      setInfo(i);
      setMcp(m);
    } catch (err) {
      const msg = err instanceof ApiError ? err.message : "加载系统状态失败";
      addError(msg, "设置");
    } finally {
      setLoading(false);
    }
  }, [addError]);

  useEffect(() => {
    load();
  }, [load]);

  const handleExport = async () => {
    setExporting(true);
    try {
      const data = await exportData();
      const blob = new Blob([JSON.stringify(data, null, 2)], {
        type: "application/json",
      });
      const url = URL.createObjectURL(blob);
      const a = document.createElement("a");
      a.href = url;
      a.download = `personal-ai-backup-${new Date().toISOString().slice(0, 10)}.json`;
      a.click();
      URL.revokeObjectURL(url);
    } catch (err) {
      const msg = err instanceof ApiError ? err.message : "导出失败";
      addError(msg, "设置");
    } finally {
      setExporting(false);
    }
  };

  const handleImport = async (e: React.ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0];
    if (!file) return;
    setImporting(true);
    try {
      const text = await file.text();
      const data = JSON.parse(text);
      const writeImport = importConfirm === "DESTROY_AND_IMPORT";
      await importData(data, !writeImport);
      if (writeImport) setImportConfirm("");
      await load();
    } catch (err) {
      const msg = err instanceof ApiError ? err.message : "导入失败";
      addError(msg, "设置");
    } finally {
      setImporting(false);
      e.target.value = "";
    }
  };

  const updateProvider = (index: number, patch: Partial<LlmProviderConfig>) => {
    setLlmForm((prev) =>
      prev.map((p, i) => (i === index ? { ...p, ...patch } : p))
    );
  };

  const applyPreset = (index: number, presetId: string) => {
    const preset = llmSettings?.presets[presetId];
    if (!preset) return;
    updateProvider(index, {
      id: presetId,
      name: preset.name,
      type: preset.type as LlmProviderConfig["type"],
      base_url: preset.base_url,
      model: preset.model,
      api_key: preset.type === "ollama" ? "ollama" : "",
    });
  };

  const addProvider = () => {
    const id = `custom-${Date.now()}`;
    setLlmForm((prev) => [...prev, emptyProvider(id)]);
  };

  const removeProvider = (index: number) => {
    setLlmForm((prev) => prev.filter((_, i) => i !== index));
  };

  const handleSaveLlm = async () => {
    setSavingLlm(true);
    try {
      const result = await updateLlmSettings({
        default_provider: llmDefault,
        temperature: llmTemperature,
        max_tokens: llmMaxTokens,
        providers: llmForm,
      });
      applyLlmSettings({
        ...llmSettings!,
        ...result,
        presets: result.presets ?? llmSettings?.presets ?? {},
        provider_types: result.provider_types ?? llmSettings?.provider_types ?? {},
      });
    } catch (err) {
      addError(err instanceof ApiError ? err.message : "保存 LLM 配置失败", "设置");
    } finally {
      setSavingLlm(false);
    }
  };

  const handleTestLlm = async (providerId: string) => {
    setTestingLlm(providerId);
    try {
      const result = await testLlmConnection(providerId);
      if (!result.ok) {
        addError(result.error || "连接测试失败", "LLM");
      }
    } catch (err) {
      addError(err instanceof ApiError ? err.message : "连接测试失败", "LLM");
    } finally {
      setTestingLlm(null);
    }
  };

  const handleSaveEmail = async () => {
    setSavingEmail(true);
    try {
      const result = await updateEmailSettings({
        user: emailUser,
        password: emailPass,
        imap_host: emailSettings?.config.imap_host || "imap.gmail.com",
        smtp_host: emailSettings?.config.smtp_host || "smtp.gmail.com",
        smtp_port: emailSettings?.config.smtp_port || 465,
      });
      applyEmailSettings({
        ...(emailSettings ?? {
          provider: "gmail",
          help: "使用 Gmail 应用专用密码",
        }),
        config: result.config,
      });
    } catch (err) {
      addError(err instanceof ApiError ? err.message : "保存邮箱配置失败", "设置");
    } finally {
      setSavingEmail(false);
    }
  };

  const handleTestEmail = async () => {
    setTestingEmail(true);
    try {
      const result = await testEmailConnection();
      setEmailTestResult(result);
      if (!result.ok) {
        addError(result.error || "邮箱连接测试失败", "邮箱");
      }
    } catch (err) {
      addError(err instanceof ApiError ? err.message : "邮箱连接测试失败", "邮箱");
    } finally {
      setTestingEmail(false);
    }
  };

  if (loading && !settingsReady) {
    return (
      <div className="flex-1 flex items-center justify-center gap-2 text-gray-500">
        <Spinner />
        加载设置…
      </div>
    );
  }

  if (!settingsReady) {
    return (
      <div className="flex-1 flex flex-col items-center justify-center gap-4 text-gray-500 p-6">
        <p>{loadError || "无法加载已保存的配置"}</p>
        <Button onClick={load}>重试</Button>
      </div>
    );
  }

  return (
    <div className="flex-1 overflow-y-auto p-6">
      <div className="max-w-3xl mx-auto space-y-6">
        <div>
          <h2 className="text-2xl font-bold text-gray-100">设置</h2>
          <p className="text-sm text-gray-500 mt-1">
            系统状态、LLM 与邮箱配置、数据主权管理
          </p>
        </div>

        <Card>
          <h3 className="text-sm font-medium text-gray-300 mb-3">系统状态</h3>
          <div className="grid grid-cols-2 gap-4 text-sm">
            <div>
              <span className="text-gray-500">运行状态</span>
              <p className="mt-1">
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
                    ? "正常"
                    : health?.status === "degraded"
                      ? "降级"
                      : health?.status || "未知"}
                </Badge>
              </p>
            </div>
            <div>
              <span className="text-gray-500">版本</span>
              <p className="text-gray-200">{health?.version}</p>
            </div>
            <div>
              <span className="text-gray-500">认证</span>
              <p className="text-gray-200">
                {health?.auth_required ? "已启用" : "未启用"}
              </p>
            </div>
            <div>
              <span className="text-gray-500">对话</span>
              <p className="text-gray-200">{info?.conversations ?? 0}</p>
            </div>
            <div>
              <span className="text-gray-500">目标 / 记忆</span>
              <p className="text-gray-200">
                {info?.goals ?? 0} / {info?.memories ?? 0}
              </p>
            </div>
          </div>
          {health?.startup?.checks?.mcp &&
            health.startup.checks.mcp.failed > 0 && (
              <div className="mt-4 p-3 bg-amber-900/20 border border-amber-700/30 rounded-lg text-xs text-amber-300">
                MCP 服务 {health.startup.checks.mcp.connected}/
                {health.startup.checks.mcp.total} 已连接，
                {health.startup.checks.mcp.failed} 个连接失败。部分工具可能不可用。
              </div>
            )}
          {(health?.startup?.warning_count ?? 0) > 0 &&
            health?.status === "degraded" &&
            !(health?.startup?.checks?.mcp && health.startup.checks.mcp.failed > 0) && (
              <div className="mt-4 p-3 bg-amber-900/20 border border-amber-700/30 rounded-lg text-xs text-amber-300">
                系统存在 {health.startup?.warning_count} 项启动警告，部分功能可能受限。
              </div>
            )}
        </Card>

        <Card>
          <h3 className="text-sm font-medium text-gray-300 mb-3">LLM 配置</h3>
          <p className="text-xs text-gray-500 mb-4">
            支持 OpenAI 兼容 API 与 Ollama 本地模型。配置保存在数据库 app_settings 表，无需重启后端。
          </p>

          <div className="grid grid-cols-3 gap-3 mb-4">
            <div>
              <label className="text-xs text-gray-500 block mb-1">默认 Provider</label>
              <select
                value={llmDefault}
                onChange={(e) => setLlmDefault(e.target.value)}
                className="w-full bg-gray-800 border border-gray-700 rounded-lg px-3 py-2 text-sm text-gray-100"
              >
                {llmForm.map((p) => (
                  <option key={p.id} value={p.id}>
                    {p.name || p.id}
                  </option>
                ))}
              </select>
            </div>
            <div>
              <label className="text-xs text-gray-500 block mb-1">Temperature</label>
              <Input
                type="number"
                step="0.1"
                min="0"
                max="2"
                value={llmTemperature}
                onChange={(e) => setLlmTemperature(parseFloat(e.target.value) || 0)}
              />
            </div>
            <div>
              <label className="text-xs text-gray-500 block mb-1">Max Tokens</label>
              <Input
                type="number"
                min="256"
                value={llmMaxTokens}
                onChange={(e) => setLlmMaxTokens(parseInt(e.target.value, 10) || 4096)}
              />
            </div>
          </div>

          <div className="space-y-4">
            {llmForm.map((provider, index) => {
              const status = llmSettings?.providers_status.find(
                (s) => s.name === provider.id
              );
              return (
                <div
                  key={`${provider.id}-${index}`}
                  className="border border-gray-800 rounded-lg p-4 space-y-3"
                >
                  <div className="flex items-center justify-between">
                    <div className="flex items-center gap-2">
                      <span className="text-sm text-gray-200">
                        {provider.name || provider.id}
                      </span>
                      {status && (
                        <Badge tone={status.available ? "success" : "danger"}>
                          {status.available ? "可用" : "不可用"}
                        </Badge>
                      )}
                      {provider.id === llmDefault && (
                        <Badge tone="default">默认</Badge>
                      )}
                    </div>
                    <div className="flex gap-2">
                      <Button
                        variant="ghost"
                        size="sm"
                        onClick={() => handleTestLlm(provider.id)}
                        disabled={testingLlm === provider.id}
                      >
                        {testingLlm === provider.id ? "测试中…" : "测试"}
                      </Button>
                      {llmForm.length > 1 && (
                        <Button
                          variant="ghost"
                          size="sm"
                          onClick={() => removeProvider(index)}
                        >
                          删除
                        </Button>
                      )}
                    </div>
                  </div>

                  <div className="flex gap-2 flex-wrap">
                    {Object.keys(llmSettings?.presets ?? {}).map((presetId) => (
                        <button
                          key={presetId}
                          type="button"
                          onClick={() => applyPreset(index, presetId)}
                          className="px-2 py-1 text-xs rounded bg-gray-800 hover:bg-gray-700 text-gray-400"
                        >
                          {llmSettings?.presets?.[presetId]?.name ?? presetId}
                        </button>
                      ))}
                  </div>

                  <div className="grid grid-cols-2 gap-3">
                    <div>
                      <label className="text-xs text-gray-500 block mb-1">ID</label>
                      <Input
                        value={provider.id}
                        onChange={(e) => updateProvider(index, { id: e.target.value })}
                      />
                    </div>
                    <div>
                      <label className="text-xs text-gray-500 block mb-1">显示名称</label>
                      <Input
                        value={provider.name}
                        onChange={(e) => updateProvider(index, { name: e.target.value })}
                      />
                    </div>
                    <div>
                      <label className="text-xs text-gray-500 block mb-1">类型</label>
                      <select
                        value={provider.type}
                        onChange={(e) =>
                          updateProvider(index, {
                            type: e.target.value as LlmProviderConfig["type"],
                            api_key:
                              e.target.value === "ollama" ? "ollama" : provider.api_key,
                          })
                        }
                        className="w-full bg-gray-800 border border-gray-700 rounded-lg px-3 py-2 text-sm text-gray-100"
                      >
                        <option value="openai_compatible">OpenAI 兼容</option>
                        <option value="ollama">Ollama 本地</option>
                      </select>
                    </div>
                    <div>
                      <label className="text-xs text-gray-500 block mb-1">模型</label>
                      <Input
                        value={provider.model}
                        onChange={(e) => updateProvider(index, { model: e.target.value })}
                        placeholder="deepseek-chat / gpt-4o / qwen2.5:7b"
                      />
                    </div>
                    <div className="col-span-2">
                      <label className="text-xs text-gray-500 block mb-1">Base URL</label>
                      <Input
                        value={provider.base_url}
                        onChange={(e) => updateProvider(index, { base_url: e.target.value })}
                        placeholder="https://api.deepseek.com/v1"
                      />
                    </div>
                    <div className="col-span-2">
                      <label className="text-xs text-gray-500 block mb-1">API Key</label>
                      <PasswordInput
                        value={provider.api_key}
                        isSavedSecret={
                          Boolean(provider.has_api_key && provider.api_key === MASKED_SECRET)
                        }
                        onChange={(e) => updateProvider(index, { api_key: e.target.value })}
                        placeholder={
                          provider.type === "ollama" ? "ollama（可留空）" : "留空则使用 .env 中的密钥"
                        }
                      />
                      {provider.has_api_key && provider.api_key === MASKED_SECRET && (
                        <p className="text-xs text-gray-600 mt-1">已保存密钥，留空则不修改</p>
                      )}
                    </div>
                  </div>

                  <label className="flex items-center gap-2 text-xs text-gray-400">
                    <input
                      type="checkbox"
                      checked={provider.enabled}
                      onChange={(e) =>
                        updateProvider(index, { enabled: e.target.checked })
                      }
                      className="rounded"
                    />
                    启用此 Provider
                  </label>
                </div>
              );
            })}
          </div>

          <div className="flex gap-3 mt-4">
            <Button variant="ghost" size="sm" onClick={addProvider}>
              添加 Provider
            </Button>
            <Button onClick={handleSaveLlm} disabled={savingLlm}>
              {savingLlm ? "保存中…" : "保存 LLM 配置"}
            </Button>
          </div>
          <p className="text-xs text-gray-600 mt-3">
            当前默认模型：{llmSettings?.default_model || "—"}
          </p>
        </Card>

        <Card>
          <h3 className="text-sm font-medium text-gray-300 mb-3">Gmail 邮箱配置</h3>
          <p className="text-xs text-gray-500 mb-4">
            {emailSettings?.help || "使用 Gmail 应用专用密码连接 IMAP/SMTP。"}
          </p>

          <div className="space-y-3">
            <div>
              <label className="text-xs text-gray-500 block mb-1">Gmail 地址</label>
              <Input
                type="email"
                value={emailUser}
                onChange={(e) => setEmailUser(e.target.value)}
                placeholder="your-email@gmail.com"
              />
            </div>
            <div>
              <label className="text-xs text-gray-500 block mb-1">应用专用密码</label>
              <PasswordInput
                value={emailPass}
                isSavedSecret={emailPass === MASKED_SECRET}
                onChange={(e) => setEmailPass(e.target.value)}
                placeholder="16 位应用专用密码"
              />
              {emailPass === MASKED_SECRET && (
                <p className="text-xs text-gray-600 mt-1">已保存密码，留空则不修改</p>
              )}
            </div>
          </div>

          {emailTestResult && (
            <div className="mt-3 flex gap-2 text-xs">
              <Badge tone={emailTestResult.imap_ok ? "success" : "danger"}>
                IMAP {emailTestResult.imap_ok ? "正常" : "失败"}
              </Badge>
              <Badge tone={emailTestResult.smtp_ok ? "success" : "danger"}>
                SMTP {emailTestResult.smtp_ok ? "正常" : "失败"}
              </Badge>
            </div>
          )}

          <div className="flex gap-3 mt-4">
            <Button onClick={handleSaveEmail} disabled={savingEmail}>
              {savingEmail ? "保存中…" : "保存邮箱配置"}
            </Button>
            <Button
              variant="ghost"
              onClick={handleTestEmail}
              disabled={testingEmail}
            >
              {testingEmail ? "测试中…" : "测试连接"}
            </Button>
          </div>
        </Card>

        <Card>
          <h3 className="text-sm font-medium text-gray-300 mb-3">MCP 服务器</h3>
          {!mcp?.enabled ? (
            <p className="text-sm text-gray-500">外部 MCP 未启用</p>
          ) : (
            <div className="space-y-2">
              {mcp.servers.map((s) => (
                <div
                  key={s.name}
                  className="flex items-center justify-between text-sm py-1"
                >
                  <span className="text-gray-300">{s.name}</span>
                  <div className="flex items-center gap-2">
                    <span className="text-xs text-gray-500">
                      {s.tool_count} 工具
                    </span>
                    <Badge tone={STATUS_TONE[s.status] || "default"}>
                      {STATUS_LABELS[s.status] || s.status}
                    </Badge>
                  </div>
                </div>
              ))}
              <p className="text-xs text-gray-600 mt-2">
                共 {mcp.total_tools} 个外部工具已注册
              </p>
            </div>
          )}
        </Card>

        <Card>
          <h3 className="text-sm font-medium text-gray-300 mb-3">数据主权</h3>
          <p className="text-sm text-gray-500 mb-4">
            导出完整个人数据快照，或从备份文件导入。
          </p>
          <div className="flex flex-wrap gap-3 items-center">
            <Button onClick={handleExport} disabled={exporting}>
              {exporting ? "导出中…" : "导出全部数据"}
            </Button>
            <label className="inline-block">
              <span className="inline-flex px-4 py-2 text-sm rounded-lg font-medium bg-gray-700 hover:bg-gray-600 text-gray-100 cursor-pointer">
                {importing ? "导入中…" : "导入备份（只读）"}
              </span>
              <input
                type="file"
                accept=".json"
                className="hidden"
                onChange={handleImport}
                disabled={importing}
              />
            </label>
          </div>
          <div className="mt-4 flex gap-2 items-center">
            <Input
              value={importConfirm}
              onChange={(e) => setImportConfirm(e.target.value)}
              placeholder="写入导入请输入 DESTROY_AND_IMPORT"
              className="flex-1 text-xs"
            />
            <label className="shrink-0">
              <span
                className={`inline-flex px-3 py-1.5 text-xs rounded-lg font-medium cursor-pointer ${
                  importing || importConfirm !== "DESTROY_AND_IMPORT"
                    ? "bg-gray-800 text-gray-600 cursor-not-allowed"
                    : "bg-red-700 hover:bg-red-600 text-white"
                }`}
              >
                覆盖导入
              </span>
              <input
                type="file"
                accept=".json"
                className="hidden"
                disabled={importing || importConfirm !== "DESTROY_AND_IMPORT"}
                onChange={async (e) => {
                  const file = e.target.files?.[0];
                  if (!file || importConfirm !== "DESTROY_AND_IMPORT") return;
                  setImporting(true);
                  try {
                    const data = JSON.parse(await file.text());
                    await importData(data, false);
                    setImportConfirm("");
                    await load();
                  } catch (err) {
                    addError(
                      err instanceof ApiError ? err.message : "覆盖导入失败",
                      "设置"
                    );
                  } finally {
                    setImporting(false);
                    e.target.value = "";
                  }
                }}
              />
            </label>
          </div>
        </Card>

        <Button variant="ghost" size="sm" onClick={load}>
          刷新状态
        </Button>
      </div>
    </div>
  );
}
