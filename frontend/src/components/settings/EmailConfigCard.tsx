import { useState } from "react";
import {
  updateEmailSettings,
  testEmailConnection,
  ApiError,
  type EmailSettingsResponse,
} from "../../api/client";
import { useErrorStore } from "../../stores/errorStore";
import Card from "../ui/Card";
import Button from "../ui/Button";
import Badge from "../ui/Badge";
import { Input, PasswordInput } from "../ui/Input";

const MASKED_SECRET = "••••••••";

interface Props {
  email: EmailSettingsResponse;
  onSaved: (next: EmailSettingsResponse) => void;
}

export default function EmailConfigCard({ email, onSaved }: Props) {
  const addError = useErrorStore((s) => s.addError);

  const [emailUser, setEmailUser] = useState(email.config.user);
  const [emailPass, setEmailPass] = useState(email.config.password);
  const [savingEmail, setSavingEmail] = useState(false);
  const [testingEmail, setTestingEmail] = useState(false);
  const [emailTestResult, setEmailTestResult] = useState<{
    ok: boolean;
    imap_ok: boolean;
    smtp_ok: boolean;
    error?: string | null;
  } | null>(null);

  const handleSaveEmail = async () => {
    setSavingEmail(true);
    try {
      const result = await updateEmailSettings({
        user: emailUser,
        password: emailPass,
        imap_host: email.config.imap_host || "imap.gmail.com",
        smtp_host: email.config.smtp_host || "smtp.gmail.com",
        smtp_port: email.config.smtp_port || 465,
      });
      onSaved({
        provider: email.provider,
        help: email.help,
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
        imap_host: email.config.imap_host || "imap.gmail.com",
        smtp_host: email.config.smtp_host || "smtp.gmail.com",
        smtp_port: email.config.smtp_port || 465,
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

  return (
    <Card>
      <h3 className="text-sm font-medium text-gray-300 mb-3">Gmail 邮箱配置</h3>
      <p className="text-xs text-gray-500 mb-4">
        {email.help || "使用 Gmail 应用专用密码连接 IMAP/SMTP。"}
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
  );
}
