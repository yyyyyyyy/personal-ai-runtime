# Reality Verification Report

## Verification Metadata
- **Timestamp**: 2026-06-30 12:45:00 UTC
- **Constitution Version**: v3.0
- **Code Commit SHA**: 95297a8225ee3bc48b75ff8d975c3adc84ed32d0
- **Truth Audit Reference**: `docs/engineering/TRUTH_AUDIT.md`

---

## 1. Invariant Compliance

| Invariant ID | Description | Status | Severity |
|-------------|-------------|--------|----------|
| I-001 | Kernel 是唯一写入口 | ❌ FAIL | MEDIUM |
| I-002 | 投影表与事件日志一致 | ✅ PASS | — |
| I-003 | 能力调用经过 4-Gate 裁决 | ✅ PASS | — |
| I-004 | Agent 不可写入 GOVERNED 表 | ✅ PASS | — |
| I-005 | 数据主权操作可执行 | ❌ FAIL | MEDIUM |
| I-006 | ChromaDB ↔ SQLite 一致性 | ✅ PASS | — |
| I-007 | 调度器恢复完整 | ✅ PASS | — |

### Violation Details

#### I-001: Kernel 是唯一写入口 — ❌ FAIL (MEDIUM)

**Violation**: CI 边界扫描脚本 `scripts/check_boundary.py` 的 PROJECTION_TABLES 列表不完整，存在覆盖缺口。

| 表名 | table_registry 分类 | check_boundary 扫描 | 影响 |
|------|---------------------|---------------------|------|
| `projection_checkpoints` | GOVERNED | **未扫描** | CI 无法检测对此表的越界写入 |
| `handler_executions` | GOVERNED | **未扫描** | CI 无法检测对此表的越界写入 |
| `events` | APP_STORAGE | **被误扫** | 对 APP_STORAGE 表的写入产生误报 |

**Constitution Requirement**: "所有 GOVERNED 表的 INSERT/UPDATE/DELETE 必须仅通过 `kernel.emit_event() → projectors` 路径。"

**Impact**: 2 张 GOVERNED 表不受 CI 边界扫描保护。虽然当前代码中未发现对这些表的越界写入，但验证机制本身存在盲区。

---

#### I-005: 数据主权操作可执行 — ❌ FAIL (MEDIUM)

**Violation**: 宪法声明的接口与方法实际名称不匹配。

| 宪法声明 | 实际代码 | 位置 |
|----------|----------|------|
| `export_data()` | `export_event_log_rows()` | `kernel_sovereignty.py:64` |
| `import_data()` | `import_event_log_rows()` | `kernel_sovereignty.py:70` |
| `destroy_data()` | **不存在于 SovereigntyMixin** | — |

实际 `destroy_all()` 方法存在于 `DigitalLegacy` 类 (`product/digital_legacy.py:173`)，不在 Kernel 边界内。

**Constitution Requirement**: "`export_data()`, `import_data()`, `destroy_data()` 必须无条件完成且不留余数据。"

**Impact**: 数据销毁功能在 Kernel ABI 中不可用。用户必须通过 `DigitalLegacy`（App 层）执行销毁，而非通过 Kernel API。

---

#### I-002 / I-003 / I-004 / I-006 / I-007 — ✅ PASS

所有 5 个合规 Invariant 均有：
- 完整的实现代码
- 可执行的 CI 验证脚本
- 零可检测的违规

| Invariant | 关键验证 |
|-----------|----------|
| I-002 | `check_projection_provenance.py` + `verify_rebuild.py` 存在，覆盖 12 张投影表的全量重建验证 |
| I-003 | `invoke_capability()` 始终调用 `capability_gateway.decide()`；`check_execution_ownership.py` 空豁免白名单 |
| I-004 | `user_profile` 正确归类为 APP_STORAGE；直写 SQLite 作为已知偏差记录在 ADR-2026-006 |
| I-006 | `verify_vector_consistency.py` 存在；两阶段同步（预计算 embedding_id + `_sync_memory_index` 修复）完整 |
| I-007 | `Scheduler._recover()` 处理 running（转 retrying）和 pending（直接入队），通过事件驱动恢复 |

---

## 2. Boundary Integrity

| Boundary ID | Name | Interface Coverage | Cross-Boundary Violations | Status |
|-------------|------|-------------------|--------------------------|--------|
| B-001 | Kernel | 6/6 | 0 | ✅ PASS |
| B-002 | Capability Governance | 1/1 | 0 | ✅ PASS |
| B-003 | Tool Registry | 3/3 | 0 | ✅ PASS |
| B-004 | Event Dispatch | 3/3 | 0 | ✅ PASS |
| B-005 | Scheduler | 1/1 | 0 | ✅ PASS |
| B-006 | Storage | 14 GOVERNED / 11 APP_STORAGE | 0 | ✅ PASS |
| B-007 | API | Auth present | 0 | ❌ FAIL (docs drift) |
| B-008 | Governance Context | 2/2 | 0 | ✅ PASS |

### Boundary Details

**B-001 (Kernel)**: 6/6 接口完整。`emit_event()`, `query_state()`, `read_events()`, `invoke_capability()`, `request_approval()`, `submit_command()` 均在 `kernel.py` 或其 Mixin 中实现。Kernel 无 User Space 依赖。

**B-002 (Capability Governance)**: `CapabilityGateway.decide()` 是唯一授权入口。`mcp_hub.invoke_tool()` 只有一个调用者——`kernel.py:714`（`invoke_capability()` 内部）。零绕行路径。

**B-003 (Tool Registry)**: MCPHub 是唯一工具注册表。13 个类别，37 个 builtin 工具。`register_mesh_tools()` 动态注册外部 MCP 工具，但使用同一 `register_tool()` 方法。

**B-004 (Event Dispatch)**: `kernel._dispatch()` 是唯一事件分发点。`agent_bus.publish()` 只有一个调用者——`kernel.py:473`。

**B-005 (Scheduler)**: 三个独立后台循环共存（Scheduler 50ms, TimerEngine 1s, BackgroundWorker 10s），按宪法 ADR-2026-004 标记为"待统一"。

**B-006 (Storage)**: 14 GOVERNED + 11 APP_STORAGE 表分类正确。ChromaDB 作为派生索引，两阶段同步完整。

**B-008 (Governance Context)**: `ContextPipeline.build()` 和 `build_from_request()` 完整。`ExecutionContextProvider` 和 `CapabilityContextProvider` 为休眠状态（零生产调用者），符合 ADR-2026-005。

### B-007 Violation: API Boundary — 文档漂移

| 项目 | 宪法声明 | 代码实际 |
|------|----------|----------|
| API 路由组 | 17 | 16 |
| 认证白名单路径 | 5 | 6 |

16 个路由组：chat, dashboard, system, settings_api, memory, goals, notifications, tasks, telemetry_api, approvals, background_tasks, triggers, inbox, connectors, timeline, knowledge。

6 个白名单路径：`/`, `/api/system/health`, `/api/system/live`, `/docs`, `/redoc`, `/openapi.json`。

**影响**: 纯文档不一致，不影响功能。

---

## 3. Dead Code Status

| FACT ID | Item | Location | Previous Status | Current Status |
|---------|------|----------|----------------|----------------|
| FACT-38 | BeliefFormed event | `constants.py:35` | DEAD_CODE | **STILL_DEAD** — 定义但永不 emit |
| FACT-39 | AgentSpawned/AgentTerminated | `constants.py:19-20` | DEAD_CODE | **STILL_DEAD** — 仅测试 emit |
| FACT-40 | _APPLICATION_EVENT_TYPES | `legacy_event_adapter.py:49` | DEAD_CODE | **STILL_DEAD** — 仍为空 frozenset |
| FACT-41 | estimate_tokens() | `context_runtime.py:43` | DEPRECATED | **DEPRECATED** — 1 个调用者仍用 (`__post_init__`) |
| FACT-44 | RecallRanker | `user_profile.py:93` | DORMANT | **STILL_DORMANT** — 零外部导入 |
| FACT-38 | patterns/schedules 表 | `schema_ddl.py:88,190` | DEAD_CODE | **STILL_PRESENT** — DDL 和查询路径仍存在 |

---

## 4. Duplication Status

| FACT ID | Item | Location A | Location B | Current Status |
|---------|------|-----------|-----------|----------------|
| FACT-35 | 审批双路径读取 | `approval_engine.py:17` | `kernel.py:567` | **STILL_DUP** — 两者独立查询 `approvals` |
| FACT-45 | SQL 构建重复 | `kernel_query_state.py` (12 methods) | `query_builder.py` (已存在) | **STILL_DUP** — query_builder 完全未被使用 |
| FACT-37 | 通知去重过滤失效 | `background_worker.py:82` | `kernel_query_state.py:309` | **BUG CONFIRMED** — `related_id`/`notification_type` 参数不支持 |

---

## 5. Dormant Components Status

| FACT ID | Component | Previous Status | Current Status |
|---------|----------|----------------|----------------|
| FACT-36 | ExecutionContextProvider | DORMANT | **STILL_DORMANT** — 零生产调用者 |
| FACT-36 | CapabilityContextProvider | DORMANT | **STILL_DORMANT** — 零生产调用者 |
| FACT-43 | legacy_event_adapter | DORMANT/DEPRECATED | **⚠️ NOT DORMANT** — 3 个生产模块仍活跃导入 |

### legacy_event_adapter 重新分类

| 导入者 | 导入内容 | 文件 |
|--------|----------|------|
| `read_ports.py` | `recent_legacy_events` | `read_ports.py:16` |
| `api/goals.py` | `goal_legacy_events` | `goals.py:11` |
| `agents/world_model.py` | `to_legacy_dict` | `world_model.py:11` |

**修正**: Truth Audit 将此归类为 DORMANT/DEPRECATED，但实际上是 **ACTIVE**。三个生产模块依赖此适配器。删除需要先迁移这些调用者。

---

## 6. Budget Compliance

| Subsystem | Boundary ID | Cap | Actual | Usage % | Status |
|-----------|-------------|-----|--------|---------|--------|
| 调度引擎 | B-005 | 3 | 3 | 100% | ⚠️ WARN |
| 审批系统 | B-002 | 3 | 3 | 100% | ⚠️ WARN |
| 后台循环 | B-005 | 3 | 3 | 100% | ⚠️ WARN |
| Builtin 工具类别 | B-003 | ≤8 | **13** | 162% | ❌ OVER |
| Builtin 工具总数 | B-003 | ≤20 | **37** | 185% | ❌ OVER |
| API 路由组 | B-007 | ≤12 | 16 | 133% | ❌ OVER |
| Context Fragment | B-008 | ≤8 | 13 | 162% | ❌ OVER |
| GOVERNED 表 | B-006 | ≤12 | 13 | 108% | ❌ OVER |
| APP_STORAGE 表 | B-006 | ≤6 | 10 | 166% | ❌ OVER |
| 全局单例（非 Container） | — | 0 | **11** | ∞ | ❌ OVER |
| 重复系统 | — | 0 | 3 | ∞ | ❌ OVER |
| 遗留适配器 | — | 0 | 1 | ∞ | ❌ OVER |
| 死事件类型 | — | 0 | 3 | ∞ | ❌ OVER |
| 休眠治理组件 | — | 0 | 2 | ∞ | ❌ OVER |
| 未使用类 | — | 0 | 1 | ∞ | ❌ OVER |

### Budget Summary

| Status | Count | Items |
|--------|-------|-------|
| ✅ SAFE | 0 | — |
| ⚠️ WARN | 3 | 调度引擎、审批系统、后台循环 (均在 100%，待合并) |
| ❌ OVER | 12 | 工具类别、工具总数、路由组、Fragment、GOVERNED 表、APP_STORAGE 表、单例、重复系统、遗留适配器、死事件、休眠组件、未使用类 |

---

## 7. Architecture Drift

### Undocumented Components (in code but not in ARCHITECTURE.md)

无。所有代码组件均在 ARCHITECTURE.md 或 CONSTITUTION.md 中有对应定义。

### Missing Components (in ARCHITECTURE.md but not in code)

- Boundary I-005 (sovereignty): `destroy_data()` 方法在 Kernel ABI 中不存在（在 `DigitalLegacy` 中实现）

### Diverged Components (implementation differs from design)

| Component | 设计 (Constitution) | 实际 | 偏差类型 |
|-----------|---------------------|------|----------|
| I-005 方法命名 | `export_data()`, `import_data()`, `destroy_data()` | `export_event_log_rows()`, `import_event_log_rows()` | 命名偏差 |
| B-007 路由组 | 17 | 16 | 计数偏差 |
| B-007 白名单 | 5 paths | 6 paths | 计数偏差 |
| legacy_event_adapter | DORMANT (v0.3 删除) | ACTIVE (3 个调用者) | 状态偏差 |

---

## 8. Implementation Deviations

### Under-implementations

| Constitution Ref | Expected | Found | Gap |
|-----------------|----------|-------|-----|
| I-005 | `destroy_data()` on SovereigntyMixin | 不存在 | 销毁不在 Kernel ABI 中 |
| I-001 | 14 GOVERNED 表全部受 CI 扫描 | 12/14 受扫描 | `projection_checkpoints`, `handler_executions` 不在扫描列表 |

### Over-implementations

| Location | Extra Functionality | Notes |
|----------|-------------------|-------|
| `user_profile.py` | 直写 SQLite 非事件溯源 | 归类为 APP_STORAGE，宪法记录为已知偏差 |
| `context_runtime.py:estimate_tokens()` | 废弃替代实现 | 已有 `token_counter.count_text_tokens()` 但未删除 |

### Mis-implementations

| Location | Expected | Actual |
|----------|----------|--------|
| `kernel_sovereignty.py` | `export_data()` 全量导出 | `export_event_log_rows()` 仅导出 event_log |
| `kernel_sovereignty.py` | `destroy_data()` 数据销毁 | 不存在；实际在 `DigitalLegacy` |

---

## Summary

| Dimension | Pass | Fail | Pass Rate |
|-----------|------|------|-----------|
| Invariant Compliance | 5 | 2 | 71.4% |
| Boundary Integrity | 7 | 1 | 87.5% |
| Budget Compliance | 0 | 15 (3 WARN + 12 OVER) | 0% |
| Dead Code | 4 confirmed, 2 partial | — | — |
| Duplications | 3 confirmed | — | — |
| Dormant Components | 2 dormant, 1 reclassified | — | — |

### Critical Issues

1. **I-001 (MEDIUM)**: CI 边界扫描漏检 2 张 GOVERNED 表
2. **I-005 (MEDIUM)**: `destroy_data()` 方法缺失于 Kernel ABI
3. **B-007 (LOW)**: 文档计数漂移（路由组 16 vs 17, 白名单 6 vs 5）
4. **Budget OVER (HIGH)**: 12 项超预算，大部分远超上限（工具 37/20, Fragment 13/8, 单例 11/0）
5. **legacy_event_adapter (MEDIUM)**: 重新分类为 ACTIVE（3 个生产调用者）而非 DORMANT

---

**Overall Verdict**: ⚠️ **PARTIALLY COMPLIANT**

- Invariants: 5/7 compliant (71.4%) — 2 non-critical deviations
- Boundaries: 7/8 compliant (87.5%) — 1 documentation drift
- Budget: 0% compliant — 所有维度超预算或处于上限
- 关键功能完整：Event Sourcing、4-Gate 授权、调度恢复、向量一致性均在代码中完全实现

**注意**: 目前代码处于 `active=true`（IMPLEMENTATION_PLAN.md 已生成但 PR 未执行）状态。预算超标表明需要按 Implementation Plan 执行 PR-01 ~ PR-12 合并操作以修复。Compliance 不影响下一步（Stage 05 Reality Sync），但需要在下一循环的 Truth Audit 中重新评估。
