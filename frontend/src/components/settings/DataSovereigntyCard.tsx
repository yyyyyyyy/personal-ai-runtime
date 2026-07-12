import { useState } from "react";
import {
  downloadExport,
  exportEncryptedData,
  importData,
  importEncryptedData,
  destroyAllData,
  ApiError,
} from "../../api/client";
import { useErrorStore } from "../../stores/errorStore";
import { useInvalidateSettings } from "../../hooks/useSettingsQuery";
import Card from "../ui/Card";
import Button from "../ui/Button";
import { Input } from "../ui/Input";

interface Props {
  /** Called after a successful import so the parent can refetch core settings. */
  onAfterImport?: () => void;
}

export default function DataSovereigntyCard({ onAfterImport }: Props) {
  const addError = useErrorStore((s) => s.addError);
  const invalidateSettings = useInvalidateSettings();

  const [exporting, setExporting] = useState(false);
  const [importing, setImporting] = useState(false);
  const [importConfirm, setImportConfirm] = useState("");
  const [encryptPassword, setEncryptPassword] = useState("");
  const [encryptExporting, setEncryptExporting] = useState(false);
  const [encryptImporting, setEncryptImporting] = useState(false);
  const [destroying, setDestroying] = useState(false);
  const [statusMessage, setStatusMessage] = useState<string | null>(null);

  const reload = () => {
    invalidateSettings();
    onAfterImport?.();
  };

  const handleExport = async () => {
    setExporting(true);
    try {
      await downloadExport();
    } catch (err) {
      addError(err instanceof ApiError ? err.message : "导出失败", "设置");
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
      addError(err instanceof ApiError ? err.message : "导入失败", "设置");
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
      addError(err instanceof ApiError ? err.message : "加密导出失败", "设置");
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
      addError(err instanceof ApiError ? err.message : "销毁失败", "设置");
    } finally {
      setDestroying(false);
    }
  };

  return (
    <Card>
      <h3 className="text-sm font-medium text-gray-300 mb-3">数据主权</h3>
      <p className="text-sm text-gray-500 mb-4">导出完整个人数据快照，或从备份文件导入。</p>
      {statusMessage && <p className="text-xs text-emerald-400 mb-3">{statusMessage}</p>}
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
          <Button onClick={handleEncryptedExport} disabled={encryptExporting || !encryptPassword}>
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
        <p className="text-xs text-gray-600 mt-1">永久删除所有对话、记忆、目标和事件。不可恢复。</p>
      </div>
    </Card>
  );
}
