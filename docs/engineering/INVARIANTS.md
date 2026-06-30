# INVARIANTS

> 本文档定义 CI 强制的不可违反规则。
> 每条不变量必须有一种**机器可验证的方式**。
> 本文档不引用具体测试文件——引用 CI check 名称。

---

## Tier 1 — CI 强制的核心不变量

这些不变量在每次 CI 运行中自动验证。违反任意一条 = 构建失败。

### INV-1 · 事件日志只追加

**陈述**：event_log 表只能 INSERT，不能 UPDATE 或 DELETE。已写入的事件不可修改。

**验证**：` backend/scripts/verify_rebuild.py` — 重建验证隐式证明 event_log 未被修改（重建出的投影必须与当前投影完全一致）。

### INV-2 · 事件日志全局有序

**陈述**：event_log.seq 是严格单调递增的。没有间隙，没有重复。

**验证**：`backend/scripts/verify_rebuild.py` — 重建过程依赖 seq 有序性；间隙会导致重建失败。

### INV-3 · 投影表仅由 Kernel 写入

**陈述**：GOVERNED 表（14 张）只能通过 `kernel.emit_event()` → Projector 路径写入。应用代码不得直接 INSERT/UPDATE/DELETE 这些表。

**验证**：`backend/scripts/check_boundary.py` — 扫描所有 `.py` 文件，检测向 GOVERNED 表的直接写入。

### INV-4 · 投影可从事件日志确定性重建

**陈述**：丢弃所有投影表后，仅凭 event_log 即可重建出与当前投影完全一致的数据。

**验证**：`backend/scripts/verify_rebuild.py` — 实际执行重建并逐行对比。

### INV-5 · 所有 invoke_capability 携带 execution_id

**陈述**：任何 `invoke_capability()` 调用必须在 ExecutionContext 内，携带 `execution_id`。

**验证**：`backend/scripts/check_execution_ownership.py` — 扫描调用点并验证参数完整性。

### INV-6 · 投影行可追溯到事件日志

**陈述**：每个投影表行的存在必须有对应的事件日志条目作为来源。

**验证**：`backend/scripts/check_projection_provenance.py` — 验证投影行到事件日志的追溯。

### INV-7 · 数据导出/导入往返完整

**陈述**：任意数据导出后导入，状态与导出前必须一致（核心聚合类型）。

**验证**：`backend/scripts/verify_export_roundtrip.py` — 执行实际导出→导入→对比。

### INV-8 · SQLite-ChromaDB 向量索引一致

**陈述**：memories 表中的 embedding_id 必须与 ChromaDB 中的索引一致。不一致的记录在修复队列中。

**验证**：`backend/scripts/verify_vector_consistency.py` — 交叉验证两端的 ID 集合。

### INV-9 · 对话历史可从事件日志重建

**陈述**：丢弃 conversations 和 messages 投影表后，可仅凭 event_log 中的 ConversationCreated、MessageAppended 等事件完全重建对话视图。

**验证**：`backend/scripts/verify_conversation_rebuild.py`。

### INV-10 · 目标可从事件日志重建

**陈述**：丢弃 goals、actions、tasks 投影表后，可仅凭 event_log 中的 GoalCreated、GoalUpdated、TaskCreated 等事件完全重建目标视图。

**验证**：`backend/scripts/verify_goal_rebuild.py`。

### INV-11 · 审批过期自动执行

**陈述**：超过 24 小时的待处理审批必须自动标记为过期，审批状态变更仅通过 ApprovalRequested/Granted/Denied/Expired 事件触发。

**验证**：`backend/scripts/verify_memory_lifecycle.py` — 包含审批生命周期测试。

### INV-12 · LLM 出站可审计

**陈述**：所有 LLM API 调用（请求内容、响应内容、工具调用）必须记录在 LLM 出站审计日志中。

**验证**：`backend/scripts/verify_egress.py`。

### INV-13 · 文件系统操作受 URL 安全保护

**陈述**：fetch_url 和 web_search 工具必须经过 SSRF 防护（`url_safety.py`）。

**验证**：单元测试确保危险 URL 被阻止。

---

## Tier 2 — 架构约束（不阻塞 CI，但需最终收敛）

这些规则对架构健康至关重要，但验证方式非自动化（或自动化程度不完整）。目标是在未来提升到 Tier 1。

### INV-P1 · 无循环依赖

**陈述**：模块间的 import 图必须是 DAG。Kernel 不 import User Space 的任何模块。

**当前验证**：mypy type check（CI 的一部分）。

### INV-P2 · RuntimeContainer 是子系统唯一访问点

**陈述**：所有 Runtime 子系统通过 `RuntimeContainer` 访问，不应有分散的模块级单例。

**当前验证**：代码审查。

### INV-P3 · Handler 不持有状态

**陈述**：`@subscribe` 装饰的 Handler 函数是无状态的。状态只存在于投影表和 event_log 中。

**当前验证**：代码审查 + 测试隔离（每个测试重置 RuntimeContainer）。

### INV-P4 · Fragment 不拥有数据

**陈述**：Context Fragment 只读取投影数据（通过 ReadPorts），不写入任何数据。

**当前验证**：代码审查 + `check_boundary.py`（间接：确保 Fragment 不写 GOVERNED 表）。

### INV-P5 · 新的能力必须有策略

**陈述**：任何新增的能力（工具）必须同步定义其 `risk_level` 和 `requires_confirmation` 策略。

**当前验证**：CI 验证 MCP 工具注册数 ≥ 28 且确认门正确。
