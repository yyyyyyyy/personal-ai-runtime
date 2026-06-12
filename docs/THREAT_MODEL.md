# Threat Model · Personal AI Runtime

> 状态：**v0.9 — Active** ｜ 底座聚焦阶段

## 信任边界

```text
外部世界（邮件 / 网页 / 文件 / Shell）
        ↓  不可信输入
   Agent 上下文（Brain + 工具循环）
        ↓  治理闸门
   Kernel（invoke_capability + Approval）
        ↓  审计
   本地存储 / 出站 LLM API
```

**核心威胁：** 不可信外部内容通过 Prompt Injection 诱导 Agent 自动执行写类工具（文件、Shell、发信），绕过用户对「高风险操作」的感知。

## 攻击面

| 向量 | 路径 | 严重性 |
|------|------|--------|
| Prompt Injection | 邮件/网页 → 对话上下文 → 自动 tool-call | **Critical** |
| 越权工具调用 | 低风险工具链组合 | High |
| 数据出站 | LLM API 携带个人上下文 | Medium |
| 本地提权 | Shell / 文件系统工具 | Critical |

## 缓解措施（v0.1）

### 1. 来源污点（Taint）

- 外部摄入工具（`check_inbox`、`fetch_url`、`web_search` 等）成功后，标记当前 `correlation_id` 为 **tainted**。
- 同一 `correlation_id` 内，**写类工具**（与 `capability_policy.json` 的 `needs_user` 一致：`write_file`、`shell_exec`、`send_email` 等）强制 `risk=high`，禁止 auto-allow。
- 实现：`app/core/runtime/taint.py` + `kernel.invoke_capability` 升级逻辑。

### 2. Approval 治理

- 所有能力经 `invoke_capability`；高风险需用户在前端确认。
- 策略表：`capability_policy` + `sensitive_router`。

### 3. Egress 审计（非脱敏边界）

- 出站 LLM 调用记录 `EgressApproved` 事件（审计日志）。
- **不**声称完整 PII 脱敏；当前仅做出站审计，不做脱敏边界。

### 4. API 认证（opt-in）

- 单用户 Bearer token：设置 `AUTH_TOKEN` 后，HTTP API 需 `Authorization: Bearer <token>`。
- WebSocket（`/ws`）通过 `Sec-WebSocket-Protocol: auth.<token>` 传 token（不出现在 URL 中）。
- 前端 / Desktop 通过 `VITE_AUTH_TOKEN`（与 `AUTH_TOKEN` 一致）注入 token。
- **默认绑定 `127.0.0.1`**；绑定 `0.0.0.0` 或局域网暴露时**必须**设置 `AUTH_TOKEN`。
- **默认关闭**：未设置 `AUTH_TOKEN` 且仅 localhost 监听时，不拦截请求，适合本地开发。

### 5. 工具层网络与执行边界

- **SSRF**：`fetch_url` / `open_web_page` 经 `url_safety.validate_http_url` 拒绝内网、localhost、metadata 地址；重定向目标二次校验。
- **Shell**：`shell_exec` 禁用 `shell=True`，argv 白名单 + 禁止管道/重定向/解释器 `-c`；`curl`/`wget` 的 http(s) 参数同样走 URL 安全校验。
- **文件系统**：允许目录用 `Path.is_relative_to()` 判断，防止前缀绕过。
- **数据主权 API**：`export` / 破坏性 `import` / `destroy` 需显式确认码。

## 非目标（当前版本）

- 多用户隔离
- 网络级沙箱
- 完整 PII NER 脱敏

## 验证

```bash
make boundary
python -m pytest tests/runtime/test_taint.py tests/runtime/test_shell_server.py \
  tests/runtime/test_url_safety.py tests/runtime/test_fetch_ssrf.py \
  tests/runtime/test_filesystem_server.py tests/integration/test_system_api.py -q
```
