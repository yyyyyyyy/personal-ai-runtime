# Threat Model · Personal AI Runtime

> 状态：**v0.1 — Draft** ｜ 底座聚焦阶段

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
- 同一 `correlation_id` 内，**写类工具**（`write_file`、`run_shell_command`、`send_email` 等）强制 `risk=high`，禁止 auto-allow。
- 实现：`app/core/runtime/taint.py` + `kernel.invoke_capability` 升级逻辑。

### 2. Approval 治理

- 所有能力经 `invoke_capability`；高风险需用户在前端确认。
- 策略表：`capability_policy` + `sensitive_router`。

### 3. Egress 审计（非脱敏边界）

- 出站 LLM 调用记录 `EgressApproved` 事件（审计日志）。
- **不**声称完整 PII 脱敏；当前仅做出站审计，不做脱敏边界。

### 4. API 认证（opt-in）

- 单用户 Bearer token：设置 `AUTH_TOKEN` 后，HTTP API 需 `Authorization: Bearer <token>`。
- WebSocket（`/ws`）使用查询参数 `?token=<token>`。
- 前端通过 `VITE_AUTH_TOKEN`（与 `AUTH_TOKEN` 一致）注入 token。
- **默认关闭**：未设置 `AUTH_TOKEN` 时不拦截请求，适合本地开发与测试。

## 非目标（当前版本）

- 多用户隔离
- 网络级沙箱
- 完整 PII NER 脱敏

## 验证

```bash
make boundary
python -m pytest tests/runtime/test_taint.py -q   # 若存在
```
