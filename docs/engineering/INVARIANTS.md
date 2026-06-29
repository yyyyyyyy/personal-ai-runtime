# INVARIANTS

> 本文档定义**永远不能被破坏的规则**——把冻结的 [NORTH_STAR](NORTH_STAR.md)（v1.0 Constitution）
> 变成可验证的工程约束。
>
> **North Star 说目标；Invariants 说今天什么会被 CI / 运行时抓住。**
>
> 区分两类：
> - **Tier 1 · 强制不变量**：**当前存在自动化验证机制**（CI 测试、CI 脚本、DDL 触发器、
>   或运行时断言/巡检）。违反时**通常**导致 CI 失败或运行时拒绝；个别机制仅记录告警（见各条「验证强度」）。
> - **Tier 2 · 声称不变量**：North Star 或架构上**应当**成立，但**尚无**可依赖的自动化验证。
>   偏差记录在 [CURRENT_STATE.md](CURRENT_STATE.md)；升级路径见 [ROADMAP](../product/ROADMAP.md)。
>
> 真正的不变量必须**可验证**。一个无法被测试或运行时检测违反的「不变量」不是不变量，是愿望。

---

## 与 North Star 的映射（读前先懂）

| North Star | Invariants 中的落地 |
|------------|---------------------|
| **P8** 真相层 vs 工程层 | Tier 1 主要约束 **Truth Layer**（event_log + 治理投影）；`APP_STORAGE` 直写见 CURRENT_STATE，不是 Tier 1 违反 |
| **P1** State **rebuild** vs Memory **re-derive** | **INV-2**：结构化 State 确定性重建；**INV-2b**：记忆事件重放；**INV-P6**：记忆语义再推导（Tier 1） |
| **P2** App ≠ Agent | **INV-4** 约束 Agent/Runtime 代码路径；Dashboard 等产品直读不构成不变量违反 |
| **P3** Agent 副作用可审计 | **INV-P1**（Tier 1 运行时 + 静态 CI）+ **INV-P7**（Tier 1 join 门禁，五表） |
| **NG8** Governance > Autonomy | 无单独编号；体现在 INV-5 / INV-6 / INV-8 |

**文档分工**（与 North Star v1.0 冻结配套）：

```text
NORTH_STAR     = 宪法（为什么）
INVARIANTS     = 法律（什么必须可证伪）
CURRENT_STATE  = 执法报告（今天做到了什么）
ROADMAP        = 立法计划（Tier 2 → Tier 1）
```

```text
rebuild（确定性）     →  同一事件流重放，投影字节级相同
re-derive（语义一致） →  换模型/再跑抽取，忠实于来源，不要求字节相同
```

---

## 如何阅读本文档

每条不变量包含：

- **陈述**：一句话规则，实现无关。
- **为什么**：违反它的后果（用来在评审时判断「这是真违规还是边界情况」）。
- **验证机制**：**今天**用什么手段强制它。引用具体的测试 / CI 脚本 / 运行时强制。
- **验证强度**：
  - **● CI/测试阻断** — 违反则 PR 合并前失败
  - **◐ 运行时检测** — 生产路径有自动校验，可能仅告警（不中断请求）
  - **○ 声称** — 无可靠自动检测

> 注意：不变量本身是稳定的，但「验证机制」会演进。当某条声称不变量获得验证机制后，
> 它从 Tier 2 升级到 Tier 1。

---

# Tier 1 · 强制不变量

以下规则**当前有自动化验证机制**。Tier 1 不等于「每条都会在运行时 hard crash」——
见各条验证强度。PR 合并前，带 ● 的条目必须保持绿。

## Runtime Core（最小闭环）

下列四条构成 Event-Sourced Runtime 的**最小内核契约**；其余 INV 在此基础上扩展治理与安全：

```text
INV-1  Append-only Log      →  真相不可改写
INV-2  Deterministic Replay →  结构化 State 可重建
INV-3  Global Ordering      →  seq 定序因果
INV-4  Protected Boundary   →  不可信 Agent 不得直写真相层
```

当 INV-1–4 成立时，Goal / Action / Task / Approval / Memory（事件重放意义下）等均为投影，
而非第二真相源。**INV-4 是 North Star P2（Agent 不可直达真相源）的唯一可执行落地**——
Agent 本质是不可信代码；若 Agent 能 `UPDATE goals`，则 Event Log、Approval、Capability 全部失效。

---

## INV-1 · Event Log 不可变且只追加

**陈述**：`event_log` 表只允许 `INSERT`，任何 `UPDATE` 或 `DELETE` 必须被拒绝。

**为什么**：事件日志是系统的唯一真相。如果它可以被改写，「真相」就不再是真相，
所有下游投影、记忆、审计都失去可信度。

**验证机制**：
- **DDL 级触发器**（运行时强制）：`event_log_no_update` / `event_log_no_delete` 触发器
  在数据库层 `RAISE(ABORT)`，任何尝试都会在运行时立即失败。
- **测试**：`test_event_sourcing.test_event_log_is_append_only` 验证 UPDATE/DELETE 被拒。

**验证强度**：● CI/测试阻断；● 运行时拒绝（DDL trigger）

---

**陈述**：对 goal / action / task / approval / execution / policy / grant / timer /
notification / schedule / conversation 等**结构化 State 投影**，清空表后通过 `rebuild()`
重放事件流，必须得到**字节级相同**的投影。

**为什么**：这是「Event Log 是唯一真相」（North Star P1）在结构化事实上的可证伪证明。
若重建后不一致，说明存在绕过事件流的直接写入，真相分裂。

**与 Memory 的边界**：Memory 的**语义再抽取**不属于 rebuild，见 **INV-2b**（事件重放）与 **INV-P6**（re-derive）。

**验证机制**：
- **测试**（byte-identical）：`test_event_sourcing.test_rebuild_from_event_log`、
  `test_goals_event_sourced`、`test_actions_event_sourced`、
  `test_execution_events.test_rebuild_execution_matches_handler_executions`、
  `test_engine_rebuild`（task/approval engine）、`test_capability_approval.test_rebuild_approval_projection`。
- **CI 脚本**：`scripts/verify_rebuild.py`（12 张表，含 memories 行级重放——见 INV-2b）、
  `verify_snapshot_rebuild.py`、`verify_export_roundtrip.py`。

**验证强度**：● CI/测试阻断（结构化 State 投影）

---

## INV-2b · Memory 投影行由记忆事件确定性重放

**陈述**：对已落库的 `MemoryDerived` / `MemoryUpdated` / `MemoryDeleted` 等记忆类事件，
清空 `memories` 投影后 `rebuild("memory")` 必须得到字节级相同的行。

**为什么**：证明记忆**记录**未绕过事件流——与「用 GPT-5 还是从对话重新抽取」无关。
后者是 **re-derive**（INV-P6），North Star P1 的长期承诺，不要求与历史某次 LLM 输出字节相同。

**验证机制**：
- `test_engine_rebuild.test_memory_engine_rebuild`
- `verify_rebuild.py` 对 `memories` 表的字节级比对

**验证强度**：● CI/测试阻断（记忆**事件重放**，非语义再抽取）

---

## INV-3 · seq 全局单调递增

**陈述**：`event_log.seq` 由数据库 `AUTOINCREMENT` 分配，从 1 开始单调递增，是事件的全局真相顺序。
排序以 `seq` 为准，不以时间戳为准。

**为什么**：时间戳受时钟漂移影响，无法用作因果顺序的真相。`seq` 是重放与因果链的锚点。

**验证机制**：`test_event_sourcing.test_seq_is_monotonic`。

**验证强度**：● CI/测试阻断

---

## INV-4 · User Space 不得直接写受治理投影表

**陈述**：Kernel 空间之外的代码（API、Agent、App 层）不得对 `GOVERNED_TABLES`
（event_log / goals / actions / tasks / memories / approvals / handler_executions /
policy_events / grant_events / timer_events / conversations / messages / notifications /
schedules 等）执行 `INSERT / UPDATE / DELETE / SELECT`。受治理表只能由 Kernel 的
projector 在 `emit_event` 同事务内写入。

**为什么**：这是 **Governed Boundary** 的核心，也是 North Star P2 的工程落地。
Agent 是不可信代码——若治理域外的调用方能直接 DML 投影表，则 INV-1/INV-2 被绕过，
审批与能力网关形同虚设。**App（Dashboard 等）不在此列**：产品层只读或经约定通道访问，
见 North Star P2「App 不是 Agent」。

**验证机制**：
- **CI 脚本**：`scripts/check_boundary.py`（CI 步骤 "Kernel boundary guard"）扫描 `app/` 下
  所有 `.py`，检测对受治理表的直接 DML；当前 `KNOWN_VIOLATION_ALLOWLIST` 为空（零技术债务）。
- **测试**：`test_boundary_guard` 验证脚本能检测各类绕过。
- **运行时辅助**：`table_registry.py` 的 `GOVERNED_TABLES` 是受治理集合的权威定义；
  `test_projection_schema_contract.test_all_business_tables_classified` 强制每张业务表必须归类。

**验证强度**：● CI/测试阻断（`check_boundary` + schema contract）

---

## INV-5 · 能力调用必须授权，且对 agent Fail-Closed

**陈述**：任何 `invoke_capability` 调用必须经过 `CapabilityGateway.decide()`。对 `agent` 类型的
Principal，若其 `allowed_capabilities` 不包含该能力也无通配符，必须 **deny**（fail-closed），
不得 fail-open。`user` / `system` Principal 默认通配。

**为什么**：fail-open 意味着「无法判定身份时放行」——这是安全缺口，让未授权 agent 获得全部能力。
Fail-closed 是安全治理的底线。

**验证机制**：
- **测试**：`test_capability_decision.test_capability_decision_deny_principal_not_authorized`、
  `test_capability_decision.test_capability_decision_fail_closed_for_empty_agent`（空能力 agent 调任意工具被拒）、
  `test_agent_isolation.test_new_agent_instance_capability_isolation_enforced`。
- **反向测试**（防止过严）：`test_agent_isolation.test_new_agent_instance_allowed_capability_not_denied`。
- **Principal 不可变**：`test_principal.test_principal_is_frozen`（frozen dataclass）。

**验证强度**：● CI/测试阻断

---

## INV-6 · 审批绑定参数且不可重放

**陈述**：一个 `approval_id` 绑定其创建时的能力名与参数。审批通过后只能被消费一次；
篡改工具名或参数必须被拒；已消费的 approval_id 不可二次复用。

**为什么**：否则攻击者可篡改审批后的实际执行参数，或重放已用审批绕过新一次用户确认。

**验证机制**：
- `test_capability_approval.test_pre_approved_cannot_replay`（不可重放）、
  `test_capability_approval.test_pre_approved_rejects_mismatched_args`（参数绑定）。
- 集成测试 `test_approval_resolve.test_resolve_rejects_tampered_tool_name`（改 tool_name 返回 400）。

**验证强度**：● CI/测试阻断

---

## INV-7 · 受治理表与应用状态表的契约不相交且穷尽

**陈述**：每一张业务表必须且只能归入 `GOVERNED_TABLES` 或 `APP_STORAGE_TABLES` 之一，
两个集合不相交。新增业务表必须在 `table_registry.py` 显式归类。

**为什么**：这是 Kernel 边界可执行的前提。没有穷尽分类，就可能有「裸 SQL 表」绕过边界检查。

**验证机制**：`test_projection_schema_contract` 的三个测试：
`test_governed_and_app_storage_disjoint`、`test_all_business_tables_classified`、
`test_governed_projection_columns_match_contract`。

**验证强度**：● CI/测试阻断

---

## INV-8 · 来源污点（Taint）必须升级被污染链上的写操作

**陈述**：当不可信外部内容经摄入工具（check_inbox / web_search / fetch_url / browser 等）
进入推理链后，同一 `correlation_id` 上的写类工具（apply_patch / write_file / shell_exec /
send_email 等）必须被强制升级为需要用户审批（risk=high），不得自动放行。

**为什么**：这是 Prompt Injection 缓解的核心。否则邮件/网页中的恶意指令可诱导代理自动
执行破坏性动作。

**验证机制**：
- `test_taint.test_write_class_tools_match_capability_policy`（taint 写工具集 ≡ policy needs_user 集合，双向契约）。
- `test_taint.test_tainted_write_forces_high_risk` / `test_tainted_shell_exec_forces_approval`。
- `test_taint.test_kernel_marks_taint_after_external_ingestion`（Kernel 自动标污点）。

**验证强度**：● CI/测试阻断

---

## INV-9 · Scheduler 崩溃恢复不得用裸 SQL 突变 handler_executions

**陈述**：重启后的执行恢复（interrupted `running` 状态）必须通过 emit `ExecutionRetried`
事件完成状态迁移，禁止 `UPDATE handler_executions SET status=...` 直接改库。
恢复也是事件驱动的。

**为什么**：若恢复能裸 SQL 改投影，则该投影不再是「事件投影」而是「双真相」之一，
INV-2（重建一致性）在恢复路径上失效。

**验证机制**：
- `test_execution_recovery.test_recovery_no_direct_sql_mutation` —— **源码级守卫**，
  用 `inspect.getsource` 断言 `recover_work_items` 函数体不含 `UPDATE handler_executions` 字面量。
- `test_execution_recovery.test_recovery_emits_execution_retried_for_interrupted`。
- `test_execution_recovery.test_recovery_rebuild_matches_handler_executions`（恢复后重建仍字节级相等）。

**验证强度**：● CI/测试阻断

---

## INV-10 · 所有内置工具必须有策略覆盖

**陈述**：每一个注册的内置工具必须出现在 `capability_policy.json` 的 `auto_allow` / `needs_user` /
`forbidden` 之一中，且三者互斥（同一工具不能同时属于多个集合）。

**为什么**：策略缺失意味着授权决策无依据（fail-closed 会拒，但掩盖了配置错误）；
策略重叠意味着风险定义自相矛盾。

**验证机制**：`test_capability_approval.test_capability_policy_covers_all_registered_tools`
（全部内置工具覆盖 + 三类互斥 + 无多余条目；具体数量随版本演进，见 `backend/app/core/harness/mcp_hub.py`）。

**验证强度**：● CI/测试阻断

---

## INV-11 · 出站 LLM 调用必须留审计事件

**陈述**：任何出站 LLM 调用必须 emit `EgressApproved` 事件，记录分类、消息数、字符数等审计元数据。
**注意**：这是审计，不是脱敏——消息原样透传，不做 PII 改写。

**为什么**：用户需要知道「什么离开了我的机器」。即便不做脱敏，审计是事后追责与偏好学习的前提。

**验证机制**：
- `test_egress.test_egress_emits_audit_event`。
- CI 脚本 `scripts/verify_egress.py`。
- 代码自证：`egress_gate.py` 头注释明确声明「audit-only, not a redaction boundary」。

**验证强度**：● CI/测试阻断（审计；脱敏不在范围——见 NORTH_STAR NG5）

---

## INV-12 · 投影写入与事件重放在 Scheduler 热路径上零差异

**陈述**：Scheduler 每次状态转换后，实时的「投影写入」与「按事件重放重建的单行」必须完全一致，
零 mismatch。这是 Execution 作为唯一真相聚合的运行时质量门。

**为什么**：若两者有差异，意味着投影写入逻辑与重放逻辑分叉——某个时刻会无法判断哪边是真相。

**验证机制**：`test_execution_shadow_compare`（成功 / 重试 / 终态失败 / N=5 批量，CI 内 **● 阻断**）。
`execution_shadow_compare.verify_*` 在 Scheduler 热路径持续校验；不一致时记录 **WARNING**
（`execution_shadow_compare.py`），**不**中断当前 handler——属于运行时质量门，非 hard fail。

**验证强度**：● CI/测试阻断；◐ 运行时检测（告警，不中断）

---

## INV-13 · 外部摄取工具的 URL 必须经 SSRF 校验

**陈述**：`fetch_url` / `open_web_page` / `search_and_extract` 等会发起网络请求的摄入工具，
其 URL 参数必须经 `url_safety.validate_http_url` 校验，拒绝内网 / loopback / metadata / 凭证 URL，
且对重定向目标二次校验。

**为什么**：否则代理可被诱导访问内网服务（如云元数据端点 169.254.169.254）窃取凭证。

**验证机制**：`test_url_safety`、`test_fetch_ssrf`、`test_browser_ssrf`。

**验证强度**：● CI/测试阻断

---

## INV-P7 · 因果完备性（Provenance Completeness）— join 门禁（Strategy A）

**陈述**：`goals`、`approvals`、`handler_executions`、`conversations`、`messages`、`actions`、`memories` 中每一行投影必须能经 `event_log` 反查来源；
`handler_executions` 还须存在对应 `ExecutionRequested`，且非空 `event_id` 时 trigger 的 `(id, seq)` 须在 `event_log` 中存在。
`messages` 须持有非空 `source_event_id` 指向有效 event_log 行。`goals` 的 `parent_id` 若有值须在 event_log 中存在。`actions` 的 `goal_id` 若有值须在 event_log 中存在。

**为什么**：**rebuild**（INV-2）保证「能还原」；**provenance** 保证「能解释」。
本阶段采用 **join 门禁**（不新增 `source_event_*` 列）：聚合级反查 + execution trigger 校验。

**验证机制**：
- **CI 脚本**：`scripts/check_projection_provenance.py`（bootstrap 场景 + `check_provenance(conn)` join 检查）。
- **测试**：`test_projection_provenance_guard`（含 orphan fixture 必须失败）。

**验证强度**：● CI/测试阻断

**范围边界**：门禁 `goals` / `approvals` / `handler_executions` / `conversations` / `messages` / `actions` / `memories`（七表）；`messages` 额外有行级 `source_event_id` provenance 列。

---

## INV-P4 · Forbidden 能力必须在 Gate 1 被拒绝且不得执行工具

**陈述**：经 `PolicyCreated`（或等价路径）标为 `risk_level=forbidden` 的能力，`invoke_capability` 必须在 Gate 1 deny，
emit `CapabilityDenied`，且不得调用 `mcp_hub.invoke_tool`。

**为什么**：策略声明禁止却无法拦截是治理假象；仅有 deny 事件而无工具未执行证据不足以证明执法。

**验证机制**：
- **测试**：`test_capability_forbidden.test_forbidden_policy_gateway_gate1`（Gate 1 `forbidden_by_policy`）。
- **测试**：`test_capability_forbidden.test_forbidden_policy_denies_capability`（`CapabilityDenied` + `invoke_tool` 未调用）。

**验证强度**：● CI/测试阻断

**注**：生产 `capability_policy.json` 种子 `forbidden` 仍可为空；测试经隔离 Kernel 动态 `PolicyCreated` 注入，不修改种子文件。

---

## INV-P1 · 所有副作用调用必须携带有效 execution_id（运行时执法）

**陈述**：经 `kernel.invoke_capability(...)` 产生的外部副作用必须归属到 `handler_executions` 中存在的 Execution；
`CapabilityInvoked.caused_by` 须指向该 execution。

**为什么**：否则副作用「漂泊」——无法回答「这次文件写入是哪次执行干的」。North Star P3 要求 Agent 副作用可审计。

**运行时语义**（`bind_then_allow` 策略，[ROADMAP D2][ROADMAP](../product/ROADMAP.md)）：

| 场景 | 行为 |
|------|------|
| Scheduler handler 内 | `execution_scope` ContextVar 自动绑定当前 `WorkItem.id` |
| `execution_id` 显式传入 | 须存在于 `handler_executions`；否则 deny + `CapabilityDenied(invalid_execution_id)` |
| runtime actor（`agent:*` / `scheduler` / `executor` / `background`）且无有效 id | deny + `CapabilityDenied(missing_execution_id)` |
| `actor=user` 无 scope 无 id | **allow**（交互式豁免；`caused_by` 可能为空） |
| deny 路径 | 不调用 `mcp_hub.invoke_tool` |

**验证机制**：
- **CI 脚本**：`scripts/check_execution_ownership.py`（静态扫描 `invoke_capability` 须含 `execution_id` 字面量）。
- **测试**：`test_execution_ownership_guard`（CI 脚本门禁）。
- **测试**：`test_execution_ownership`（运行时 deny / ContextVar 绑定 / user 豁免 / 假 id 拒绝）。

**验证强度**：● CI/测试阻断；◐ 运行时检测（`invoke_capability` 入口执法）

**范围边界**：静态 grep 可被字面量绕过，以运行时执法为准；`user` 交互式豁免是刻意边界，非 runtime actor 漏洞。

---

## INV-P2 · Pattern / Belief 投影可由 Event Log 重建

**陈述**：Pattern 与 Belief 作为认知层投影，其**已落库事件**应可 replay（确定性重建）。

**为什么**：否则认知子系统与事件流脱节；Pattern/Belief 行成为第二真相。

**验证机制**：
- **CI 脚本**：`scripts/verify_pattern_rebuild.py`（隔离 DB，种子 `PatternDetected` → `rebuild("pattern")` 字节级一致）。
- **CI 脚本**：`scripts/verify_belief_pipeline.py`（`PatternDetected` → `BeliefFormed` → `memories` 投影 + `rebuild("memory")`）。
- **测试**：`test_a2_cognitive_ci.py`（脚本门禁 + vector 不一致检测）。

**验证强度**：● CI/测试阻断（Pattern/Belief **事件重放**；LLM 语义 re-derive 见 INV-P6）

---

## INV-P3 · SQLite 记忆投影与向量索引一致

**陈述**：`memories` 投影表与 ChromaDB `memories` collection 中的 ID 集合应保持一致。

**为什么**：否则语义检索会返回已删除的记忆，或漏掉已存在的记忆。

**验证机制**：
- **CI 脚本**：`scripts/verify_vector_consistency.py`（隔离 self-test：emit `MemoryDerived` → reconcile）。
- **测试**：`test_a2_cognitive_ci.py::test_vector_reconcile_fails_on_sqlite_chroma_mismatch`（故意不一致必须失败）。

**验证强度**：● CI/测试阻断

---

# Tier 2 · 声称不变量（尚无可靠自动验证）

以下规则是项目的真实目标，但**当前没有可依赖的自动化机制**在合并前或运行时抓住违反。
偏差见 [CURRENT_STATE.md](CURRENT_STATE.md)。获得验证机制后升级到 Tier 1。

### 升级优先级（ARB 裁决）

若资源有限，**按此顺序**将 Tier 2 升级为 Tier 1——前两项决定 Runtime 能否形成**因果闭环**：

| 优先级 | 不变量 | 理由 |
|--------|--------|------|
| ~~1~~ | ~~**INV-P1** execution ownership~~ | **已升级 Tier 1（D2）** |
| ~~2~~ | ~~**INV-P7** provenance~~ | **已升级 Tier 1（A1b）** |
| ~~3~~ | ~~INV-P4 forbidden deny~~ | **已升级 Tier 1（A3）** |
| ~~4~~ | ~~INV-P5 并发隔离~~ | **已升级 Tier 1（D1）** |
| ~~5~~ | ~~INV-P3 vector 一致性~~ | **已升级 Tier 1（A2）** |
| ~~6~~ | ~~INV-P2 Pattern/Belief rebuild~~ | **已升级 Tier 1（A2）** |
| ~~7~~ | ~~INV-P6 Memory re-derive~~ | **已升级 Tier 1（2026-06-18）** |

> 维护原则：**不要在 Tier 2 堆积**。所有 Tier 2 不变量已升级完毕。

---

## ~~INV-P1~~ · execution ownership — 已升级 Tier 1

见上文 **Tier 1 · INV-P1**（[ROADMAP A1][ROADMAP](../product/ROADMAP.md) 静态 CI + [ROADMAP D2][ROADMAP](../product/ROADMAP.md) 运行时执法）。

---

## ~~INV-P7~~ · 因果完备性 — 已升级 Tier 1

见上文 **Tier 1 · INV-P7**（[ROADMAP A1b][ROADMAP](../product/ROADMAP.md) 完成，join 门禁接入 CI）。

---

## ~~INV-P2~~ · Pattern / Belief 投影可由 Event Log 重建 — 已升级 Tier 1

见上文 **Tier 1 · INV-P2**（[ROADMAP A2][ROADMAP](../product/ROADMAP.md)：`verify_pattern_rebuild.py` + `verify_belief_pipeline.py` 接入 CI）。

---

## INV-P6 · Memory 须可重新推导（re-derive）

**陈述**：除 replay 已有 `Memory*` 事件（INV-2b）外，系统应能依据来源事实（对话、观察等）
**再次推导**语义一致的记忆。抽取模型更换或下线时，不要求与旧投影字节级相同，但须对用户事实忠实，
且推导触发可审计。

**为什么**：North Star P1 对 Memory 的承诺是 **re-derive**，不是确定性 **rebuild**。
把「记忆事件重放」与「记忆语义再抽取」混为一谈，会导致用 CI 的 byte-identical 测试
错误地绑架宪法。

**当前验证机制**：

- `verify_belief_quality.py`（CI 守护）：Belief 质量启发式检查（traceability/novelty/actionability）。
- `verify_belief_survival.py`（CI 守护）：Belief 存活率统计（survival/revocation/strengthen 指标）。
- `verify_belief_pipeline.py`（CI 守护）：Pattern → BeliefFormed → memories 投影 + rebuild。

**验证强度**：● CI/测试阻断（语义等价门禁已接入 CI，2026-06-18）

---

## ~~INV-P3~~ · SQLite 记忆投影与向量索引一致 — 已升级 Tier 1

见上文 **Tier 1 · INV-P3**（[ROADMAP A2][ROADMAP](../product/ROADMAP.md)：`verify_vector_consistency.py` 接入 CI）。

---

## ~~INV-P4~~ · Forbidden 能力 — 已升级 Tier 1

见上文 **Tier 1 · INV-P4**（[ROADMAP A3][ROADMAP](../product/ROADMAP.md) 完成，Gate 1 + 工具未执行已实测）。

---

## INV-P5 · Agent 并发隔离

**陈述**：多个 Agent 实例并发运行时，各自的事件流、checkpoint、能力授权互不干扰。

**为什么**：单用户运行时仍可能并发跑多个 handler；隔离失效会导致跨 agent 数据泄漏或授权串台。

**当前验证机制**：`test_d1_concurrent_isolation.py`（7 个测试）覆盖：
并行 `invoke_capability` taint 不交叉、并行 WorkItem actor 隔离、
`contextvars` execution_id 协程隔离、Scheduler `_MAX_CONCURRENT=8` 批处理上限、
AgentBus 并发发布不串台。`test_agent_instance` / `test_agent_isolation` 补充串行场景。

**验证强度**：● CI/测试阻断

---

## INV-R1 · Fragment Read Boundary

**陈述**：Context Fragment 不得直接访问持久化层。所有数据读取必须经 Runtime Read Ports 进入 Kernel 投影查询。

**为什么**：Fragment 是 Context Adapter，不是 Repository。直读 SQLite 绕过 Event Sourcing 边界，使投影与治理层失效。

**当前验证机制**：`tests/test_fragment_read_boundary.py` — AST 扫描 `app/fragments/` 禁止 `app.store.database`、`kernel_instance`、Agent 引擎直引等；禁止 `get_db` 字符串；数据 Fragment 必须引用 `read_ports`。

**验证强度**：● CI/测试阻断

---

# 不变量 vs 实现细节（不要混淆）

以下事项**不是**不变量，是当前实现选择。它们可以改变，不需要升级为不变量：

| 事项 | 为什么不是不变量 |
|------|----------------|
| 「用 SQLite 而非 Postgres」 | 存储引擎是实现选择；不变量是「Event Log append-only」（INV-1） |
| 「用 ChromaDB 做向量」 | 向量引擎是实现选择；不变量是记忆事件重放（INV-2b）与语义再推导（INV-P6） |
| 「Scheduler 每 N 秒轮询」 | 调度策略是实现选择；不变量是「恢复事件驱动」（INV-9） |
| 「N 个内置工具」 | 工具数量会变；不变量是「工具必须有策略」（INV-10） |
| 「四道授权 Gate」 | Gate 数量与顺序是实现选择；不变量是「授权 + fail-closed」（INV-5） |
| 「Brain / Planner / Critic」 | 具体代理是实现选择；不变量是「Agent 不进真相层」（NORTH_STAR P5） |
| 「WorkItem 是调度信封」 | WorkItem 是当前调度实现；不变量是「副作用归属 Execution」（INV-P1） |

如果你发现自己在 INVARIANTS 里写「用 X 技术」「按 Y 顺序」「每 Z 秒」——停下来。
那是实现，不是不变量。它属于 [CURRENT_STATE.md](CURRENT_STATE.md)。

---

# 维护规则

1. **新增不变量**必须能回答「违反时，什么检测机制会抓住它？」若答不出，它是 Tier 2 或不是不变量。
2. **Tier 2 不变量**必须有一条对应的 ROADMAP 条目，目标是给它装上验证机制（升级到 Tier 1）。
3. **删除不变量**是架构级决策，必须在 PR 中说明为什么它不再是项目的承诺。
4. **本文档不写实现细节**。把 SQLite / FastAPI / Brain 等名字从脑子里赶出去。
