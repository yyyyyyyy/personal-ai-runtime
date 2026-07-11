import { useEffect, useState } from "react";
import {
  exportData,
  exportEncryptedData,
  importData,
  importEncryptedData,
  destroyAllData,
  updateLlmSettings,
  testLlmConnection,
  updateEmailSettings,
  testEmailConnection,
  getPromptConfig,
  updatePromptConfig,
  ApiError,
  type LlmSettingsResponse,
  type LlmProviderConfig,
  type EmailSettingsResponse,
} from "../api/client";
import { installMcpConnector } from "../api/connectors";
import { useErrorStore } from "../stores/errorStore";
import {
  useSettingsCoreQuery,
  useSettingsHealthQuery,
  useCapabilityPolicyQuery,
  usePromptConfigQuery,
  useMcpRegistryQuery,
  useInvalidateSettings,
} from "../hooks/useSettingsQuery";
import { queryKeys } from "../hooks/useWsInvalidationBridge";
import { useQueryClient } from "@tanstack/react-query";
import { toolLabel } from "../utils/toolLabels";
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
  const invalidateSettings = useInvalidateSettings();
  const {
    data: core,
    isLoading: coreLoading,
    error: coreError,
    refetch: refetchCore,
  } = useSettingsCoreQuery();
  const { data: health, error: healthError } = useSettingsHealthQuery();

  const [llmSettings, setLlmSettings] = useState<LlmSettingsResponse | null>(null);
  const [llmForm, setLlmForm] = useState<LlmProviderConfig[]>([]);
  const [llmDefault, setLlmDefault] = useState("deepseek");
  const [llmTemperature, setLlmTemperature] = useState(0.7);
  const [llmMaxTokens, setLlmMaxTokens] = useState(4096);
  const [emailSettings, setEmailSettings] = useState<EmailSettingsResponse | null>(null);
  const [emailUser, setEmailUser] = useState("");
  const [emailPass, setEmailPass] = useState("");
  const [exporting, setExporting] = useState(false);
  const [importing, setImporting] = useState(false);
  const [importConfirm, setImportConfirm] = useState("");
  const [encryptPassword, setEncryptPassword] = useState("");
  const [encryptExporting, setEncryptExporting] = useState(false);
  const [encryptImporting, setEncryptImporting] = useState(false);
  const [destroying, setDestroying] = useState(false);
  const [savingLlm, setSavingLlm] = useState(false);
  const [savingEmail, setSavingEmail] = useState(false);
  const [testingLlm, setTestingLlm] = useState<string | null>(null);
  const [testingEmail, setTestingEmail] = useState(false);
  const [statusMessage, setStatusMessage] = useState<string | null>(null);
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

  useEffect(() => {
    if (core) {
      applyLlmSettings(core.llm);
      applyEmailSettings(core.email);
    }
  }, [core]);

  useEffect(() => {
    if (healthError) {
      const msg = healthError instanceof Error ? healthError.message : "加载系统状态失败";
      addError(msg, "设置");
    }
  }, [healthError, addError]);

  const reload = () => {
    void refetchCore();
    invalidateSettings();
  };

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

  const handleImport = async (data: Record<string, unknown>, write: boolean) => {
    setImporting(true);
    try {
      await importData(data, !write);
      if (write) setImportConfirm("");
      reload();
    } catch (err) {
      const msg = err instanceof ApiError ? err.message : "导入失败";
      addError(msg, "设置");
    } finally {
      setImporting(false);
    }
  };

  const handleImportFile = async (e: React.ChangeEvent<HTMLInputElement>, write: boolean) => {
    const file = e.target.files?.[0];
    if (!file) return;
    try {
      const data = JSON.parse(await file.text()) as Record<string, unknown>;
      await handleImport(data, write);
    } catch {
      addError("无法解析备份文件", "设置");
    } finally {
      e.target.value = "";
    }
  };

  const handleEncryptedExport = async () => {
    if (!encryptPassword) {
      addError("请输入加密密码", "设置");
      return;
    }
    setEncryptExporting(true);
    try {
      const result = await exportEncryptedData(encryptPassword);
      const blob = new Blob([JSON.stringify(result, null, 2)], { type: "application/json" });
      const url = URL.createObjectURL(blob);
      const a = document.createElement("a");
      a.href = url;
      a.download = `personal-ai-encrypted-backup-${new Date().toISOString().slice(0, 10)}.json`;
      a.click();
      URL.revokeObjectURL(url);
    } catch (err) {
      const msg = err instanceof ApiError ? err.message : "加密导出失败";
      addError(msg, "设置");
    } finally {
      setEncryptExporting(false);
    }
  };

  const handleEncryptedImport = async (e: React.ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0];
    if (!file || !encryptPassword) {
      addError("请选择文件并输入密码", "设置");
      return;
    }
    setEncryptImporting(true);
    try {
      const raw = await file.text();
      const { data, password } = JSON.parse(raw);
      await importEncryptedData(data, password || encryptPassword);
      setStatusMessage("加密导入成功");
      reload();
    } catch {
      addError("加密导入失败，请检查密码和文件", "设置");
    } finally {
      setEncryptImporting(false);
      setEncryptPassword("");
      e.target.value = "";
    }
  };

  const handleDestroy = async () => {
    if (!window.confirm("确定销毁全部个人数据？此操作不可撤销！")) return;
    setDestroying(true);
    try {
      await destroyAllData();
      setStatusMessage("数据已销毁，请重新启动应用");
    } catch (err) {
      const msg = err instanceof ApiError ? err.message : "销毁失败";
      addError(msg, "设置");
    } finally {
      setDestroying(false);
    }
  };

  const updateProvider = (index: number, patch: Partial<LlmProviderConfig>) => {
    setLlmForm((prev) => prev.map((p, i) => (i === index ? { ...p, ...patch } : p)));
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
      const result = await testEmailConnection({
        user: emailUser,
        password: emailPass,
        imap_host: emailSettings?.config.imap_host || "imap.gmail.com",
        smtp_host: emailSettings?.config.smtp_host || "smtp.gmail.com",
        smtp_port: emailSettings?.config.smtp_port || 465,
      });
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

        {statusMessage && (
          <p className="text-sm text-emerald-400 bg-emerald-950/30 border border-emerald-800/40 rounded-lg px-3 py-2">
            {statusMessage}
          </p>
        )}

        <Card>
          <h3 className="text-sm font-medium text-gray-300 mb-3">LLM 配置</h3>

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
              const status = llmSettings?.providers_status.find((s) => s.name === provider.id);
              return (
                <div
                  key={`${provider.id}-${index}`}
                  className="border border-gray-800 rounded-lg p-4 space-y-3"
                >
                  <div className="flex items-center justify-between">
                    <div className="flex items-center gap-2">
                      <span className="text-sm text-gray-200">{provider.name || provider.id}</span>
                      {status && (
                        <Badge tone={status.available ? "success" : "danger"}>
                          {status.available ? "可用" : "不可用"}
                        </Badge>
                      )}
                      {provider.id === llmDefault && <Badge tone="default">默认</Badge>}
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
                        <Button variant="ghost" size="sm" onClick={() => removeProvider(index)}>
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
                            api_key: e.target.value === "ollama" ? "ollama" : provider.api_key,
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
                        isSavedSecret={Boolean(
                          provider.has_api_key && provider.api_key === MASKED_SECRET,
                        )}
                        onChange={(e) => updateProvider(index, { api_key: e.target.value })}
                        placeholder={
                          provider.type === "ollama"
                            ? "ollama（可留空）"
                            : "留空则使用 .env 中的密钥"
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
                      onChange={(e) => updateProvider(index, { enabled: e.target.checked })}
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
            <Button variant="ghost" onClick={handleTestEmail} disabled={testingEmail}>
              {testingEmail ? "测试中…" : "测试连接"}
            </Button>
          </div>
        </Card>

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
          {health?.startup?.checks?.mcp && (
            <p className="text-xs text-gray-600 mt-2">
              状态码：
              {Object.entries(STATUS_LABELS)
                .map(([k, v]) => `${k}=${v}`)
                .join(" / ")}
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
            工具风险分级来自 capability_policy.json（与运行时闸门同一来源）。需要确认的操作可在同一对话内选择信任后自动放行。
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

        <Card>
          <h3 className="text-sm font-medium text-gray-300 mb-3">数据主权</h3>
          <p className="text-sm text-gray-500 mb-4">导出完整个人数据快照，或从备份文件导入。</p>
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
                onChange={(e) => handleImportFile(e, false)}
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
                onChange={(e) => handleImportFile(e, true)}
              />
            </label>
          </div>
          <hr className="mt-4 border-gray-800" />
          <div className="mt-4">
            <h4 className="text-xs font-medium text-gray-400 mb-2">加密备份（端到端加密）</h4>
            <div className="flex flex-wrap gap-3 items-end">
              <Input
                value={encryptPassword}
                onChange={(e) => setEncryptPassword(e.target.value)}
                placeholder="输入加密密码"
                className="flex-1 text-xs"
              />
              <Button
                onClick={handleEncryptedExport}
                disabled={encryptExporting || !encryptPassword}
              >
                {encryptExporting ? "加密导出中…" : "加密导出"}
              </Button>
              <label className="inline-block">
                <span
                  className={`inline-flex px-4 py-2 text-sm rounded-lg font-medium cursor-pointer ${encryptImporting || !encryptPassword ? "bg-gray-800 text-gray-600" : "bg-gray-700 hover:bg-gray-600 text-gray-100"}`}
                >
                  {encryptImporting ? "导入中…" : "加密导入"}
                </span>
                <input
                  type="file"
                  accept=".json"
                  className="hidden"
                  disabled={encryptImporting || !encryptPassword}
                  onChange={handleEncryptedImport}
                />
              </label>
            </div>
          </div>
          <hr className="mt-4 border-gray-800" />
          <div className="mt-4">
            <h4 className="text-xs font-medium text-red-400 mb-2">危险操作</h4>
            <Button
              onClick={handleDestroy}
              disabled={destroying}
              className="bg-red-700 hover:bg-red-600 text-white text-sm"
            >
              {destroying ? "销毁中…" : "销毁全部数据"}
            </Button>
            <p className="text-xs text-gray-600 mt-1">
              永久删除所有对话、记忆、目标和事件。不可恢复。
            </p>
          </div>
        </Card>
      </div>
    </div>
  );
}

// ── Capability trust panel (from capability_policy.json) ──────────────────

function ToolChipList({
  tools,
  tone,
}: {
  tools: string[];
  tone: "emerald" | "amber" | "red";
}) {
  const styles = {
    emerald: "bg-emerald-900/20 text-emerald-400/70 border-emerald-700/20",
    amber: "bg-amber-900/20 text-amber-400/70 border-amber-700/20",
    red: "bg-red-900/20 text-red-400/70 border-red-700/20",
  }[tone];
  if (tools.length === 0) {
    return <p className="text-xs text-gray-600">（无）</p>;
  }
  return (
    <div className="flex flex-wrap gap-1.5">
      {tools.map((id) => (
        <span key={id} className={`text-xs px-2 py-1 rounded border ${styles}`} title={id}>
          {toolLabel(id)}
        </span>
      ))}
    </div>
  );
}

function CapabilityTrustPanel() {
  const { data, isLoading, error, refetch } = useCapabilityPolicyQuery();
  const addError = useErrorStore((s) => s.addError);

  useEffect(() => {
    if (error) {
      addError(error instanceof Error ? error.message : "加载能力策略失败", "设置");
    }
  }, [error, addError]);

  if (isLoading) {
    return <p className="text-xs text-gray-600">加载策略中…</p>;
  }
  if (!data) {
    return (
      <button
        type="button"
        onClick={() => void refetch()}
        className="text-xs text-emerald-400 hover:text-emerald-300"
      >
        加载失败，点击重试
      </button>
    );
  }

  return (
    <div className="space-y-4">
      <div>
        <div className="flex items-center gap-2 mb-2">
          <span className="w-2 h-2 rounded-full bg-emerald-500" />
          <span className="text-xs font-medium text-emerald-400">自动执行</span>
          <span className="text-xs text-gray-500">— 安全操作，无需确认</span>
        </div>
        <ToolChipList tools={data.auto_allow} tone="emerald" />
      </div>
      <div>
        <div className="flex items-center gap-2 mb-2">
          <span className="w-2 h-2 rounded-full bg-amber-500" />
          <span className="text-xs font-medium text-amber-400">需要确认</span>
          <span className="text-xs text-gray-500">— 写操作 / 外发，可在对话内信任</span>
        </div>
        <ToolChipList tools={data.needs_user} tone="amber" />
      </div>
      {data.forbidden.length > 0 && (
        <div>
          <div className="flex items-center gap-2 mb-2">
            <span className="w-2 h-2 rounded-full bg-red-500" />
            <span className="text-xs font-medium text-red-400">禁止</span>
            <span className="text-xs text-gray-500">— 策略硬拦截</span>
          </div>
          <ToolChipList tools={data.forbidden} tone="red" />
        </div>
      )}
    </div>
  );
}

// ── Prompt Editor component ───────────────────────────────────────────────

function PromptEditor() {
  const addError = useErrorStore((s) => s.addError);
  const queryClient = useQueryClient();
  const { data: cfg, isLoading, error } = usePromptConfigQuery();
  const [identity, setIdentity] = useState("");
  const [codingRules, setCodingRules] = useState("");
  const [isCustomIdentity, setIsCustomIdentity] = useState(false);
  const [isCustomCodingRules, setIsCustomCodingRules] = useState(false);
  const [saving, setSaving] = useState(false);
  const [message, setMessage] = useState("");
  const [hydrated, setHydrated] = useState(false);

  useEffect(() => {
    if (error) {
      addError(error instanceof Error ? error.message : "加载人设配置失败", "设置");
    }
  }, [error, addError]);

  useEffect(() => {
    if (cfg && !hydrated) {
      setIdentity(cfg.identity);
      setCodingRules(cfg.coding_rules);
      setIsCustomIdentity(cfg.is_custom_identity);
      setIsCustomCodingRules(cfg.is_custom_coding_rules);
      setHydrated(true);
    }
  }, [cfg, hydrated]);

  const handleSave = async (field: "identity" | "coding_rules") => {
    setSaving(true);
    setMessage("");
    try {
      const payload = field === "identity" ? { identity } : { coding_rules: codingRules };
      await updatePromptConfig(payload);
      if (field === "identity") setIsCustomIdentity(!!identity.trim());
      if (field === "coding_rules") setIsCustomCodingRules(!!codingRules.trim());
      void queryClient.invalidateQueries({ queryKey: queryKeys.promptConfig });
      setMessage("已保存");
      setTimeout(() => setMessage(""), 2000);
    } catch {
      setMessage("保存失败");
    } finally {
      setSaving(false);
    }
  };

  const handleReset = async (field: "identity" | "coding_rules") => {
    setSaving(true);
    setMessage("");
    try {
      await updatePromptConfig({ [field]: "" });
      const next = await getPromptConfig();
      if (field === "identity") {
        setIdentity(next.identity);
        setIsCustomIdentity(false);
      }
      if (field === "coding_rules") {
        setCodingRules(next.coding_rules);
        setIsCustomCodingRules(false);
      }
      void queryClient.invalidateQueries({ queryKey: queryKeys.promptConfig });
      setMessage("已重置为默认");
      setTimeout(() => setMessage(""), 2000);
    } catch {
      setMessage("重置失败");
    } finally {
      setSaving(false);
    }
  };

  if (isLoading && !hydrated) {
    return <p className="text-xs text-gray-600">加载人设中…</p>;
  }

  return (
    <div className="space-y-4">
      <div>
        <div className="flex items-center justify-between mb-1.5">
          <label className="text-xs text-gray-400">
            身份定义 {isCustomIdentity && <span className="text-emerald-400">(已自定义)</span>}
          </label>
          <div className="flex gap-2">
            <button
              onClick={() => handleReset("identity")}
              disabled={saving || !isCustomIdentity}
              className="text-xs text-gray-600 hover:text-gray-400 disabled:opacity-30"
            >
              重置
            </button>
            <button
              onClick={() => handleSave("identity")}
              disabled={saving}
              className="text-xs px-2 py-0.5 bg-emerald-600 hover:bg-emerald-700 rounded text-white disabled:opacity-50"
            >
              保存
            </button>
          </div>
        </div>
        <textarea
          value={identity}
          onChange={(e) => setIdentity(e.target.value)}
          rows={6}
          className="w-full bg-gray-800 border border-gray-700 rounded-lg px-3 py-2 text-sm text-gray-300 font-mono focus:border-emerald-500 focus:outline-none resize-y"
          placeholder="定义 AI 的身份、性格、行为准则..."
        />
      </div>
      <div>
        <div className="flex items-center justify-between mb-1.5">
          <label className="text-xs text-gray-400">
            代码规则 {isCustomCodingRules && <span className="text-emerald-400">(已自定义)</span>}
          </label>
          <div className="flex gap-2">
            <button
              onClick={() => handleReset("coding_rules")}
              disabled={saving || !isCustomCodingRules}
              className="text-xs text-gray-600 hover:text-gray-400 disabled:opacity-30"
            >
              重置
            </button>
            <button
              onClick={() => handleSave("coding_rules")}
              disabled={saving}
              className="text-xs px-2 py-0.5 bg-emerald-600 hover:bg-emerald-700 rounded text-white disabled:opacity-50"
            >
              保存
            </button>
          </div>
        </div>
        <textarea
          value={codingRules}
          onChange={(e) => setCodingRules(e.target.value)}
          rows={6}
          className="w-full bg-gray-800 border border-gray-700 rounded-lg px-3 py-2 text-sm text-gray-300 font-mono focus:border-emerald-500 focus:outline-none resize-y"
          placeholder="定义 AI 编码时的行为规则..."
        />
      </div>
      {message && (
        <p className={`text-xs ${message.includes("失败") ? "text-red-400" : "text-emerald-400"}`}>
          {message}
        </p>
      )}
    </div>
  );
}

// ── MCP Marketplace Component ─────────────────────────────────────────────

function McpMarketplace() {
  const addError = useErrorStore((s) => s.addError);
  const { data: servers = [], isLoading, error, isFetched } = useMcpRegistryQuery();
  const [installing, setInstalling] = useState<string | null>(null);

  useEffect(() => {
    if (error) {
      addError(error instanceof Error ? error.message : "加载 MCP 市场失败", "设置");
    }
  }, [error, addError]);

  const handleInstall = async (name: string) => {
    setInstalling(name);
    try {
      const data = await installMcpConnector(name);
      if (data.ok) {
        alert(`"${name}" 已安装。重启后端后生效。`);
      } else {
        alert(data.message);
      }
    } catch {
      alert("安装失败");
    } finally {
      setInstalling(null);
    }
  };

  if (isLoading || !isFetched) {
    return <p className="text-xs text-gray-600">加载市场中…</p>;
  }

  const categories: Record<string, string> = {
    browser: "浏览器",
    search: "搜索",
    developer: "开发者",
    productivity: "效率",
    system: "系统",
    ai: "AI",
    communication: "通讯",
  };

  return (
    <div className="space-y-2 max-h-60 overflow-y-auto">
      {servers.length === 0 ? (
        <p className="text-xs text-gray-600">暂无可用 MCP 服务器</p>
      ) : (
        servers.map((s) => (
          <div
            key={s.name}
            className="flex items-center justify-between bg-gray-800/50 rounded-lg p-2.5"
          >
            <div className="min-w-0 flex-1">
              <div className="flex items-center gap-2">
                <span className="text-xs font-medium text-gray-300">{s.name}</span>
                <span className="text-xs px-1.5 py-0.5 bg-gray-700 rounded text-gray-500">
                  {categories[s.category] || s.category}
                </span>
              </div>
              <p className="text-xs text-gray-600 mt-0.5 truncate">{s.description}</p>
              {Object.keys(s.env_vars || {}).length > 0 && (
                <p className="text-xs text-gray-700 mt-0.5">
                  需要: {Object.keys(s.env_vars).join(", ")}
                </p>
              )}
            </div>
            <button
              onClick={() => handleInstall(s.name)}
              disabled={installing === s.name}
              className="shrink-0 ml-3 px-3 py-1 text-xs bg-gray-700 hover:bg-gray-600 text-gray-300 rounded transition-colors disabled:opacity-50"
            >
              {installing === s.name ? "安装中…" : "安装"}
            </button>
          </div>
        ))
      )}
    </div>
  );
}
