# Implementation Evolution Plan

> 基于 Architecture Constitution v3.0、Architecture Budget v3.0、ROADMAP v3.0、Truth Audit (48 FACTs) 制定。
> **本文件仅包含代码级变更计划，不修改任何代码。**
>
> **生成时间**: 2026-06-30
> **源 Commit**: 95297a8

---

## 差异分析总结

### 违反 Invariant 的代码

| Invariant | 违规代码 | FACT | 严重程度 |
|-----------|----------|------|----------|
| I-001 (Kernel 单写入口) | `UserProfile` 直写 SQLite `user_profile` 表 | FACT-26 | 中（表归类为 APP_STORAGE，但无审计） |
| I-004 (Agent 不可写 GOVERNED) | `_smart_notification_check` 查询参数不匹配，去重失效 | FACT-37 | 高（运行时 bug） |
| P3 (可审计副作用) | `user_profile` 表变更不在 event_log 中 | FACT-26 | 中 |

### 缺少实现的 Boundary

| Boundary | 缺失内容 | FACT | 优先级 |
|----------|----------|------|--------|
| B-008 (治理语境) | ExecutionContextProvider/CapabilityContextProvider 全量实现无消费者 | FACT-36 | 低（ROADMAP M6 再激活） |

### 超出预算的 Subsystem

| Subsystem | 当前 | 预算上限 | FACT | 超出 |
|-----------|------|----------|------|------|
| Builtin 工具类别 | 13 | ≤8 | FACT-27 | +5 |
| Builtin 工具总数 | 37 | ≤20 | FACT-27 | +17 |
| 后台循环 | 3 | 1 | FACT-7/12/13 | +2 |
| 审批系统 | 3 | 1 | FACT-32/35 | +2 |
| 调度引擎 | 3 | 1 | FACT-7/12/13 | +2 |

### 重复代码

| 重复内容 | FACT | 文件 |
|----------|------|------|
| 审批双路径读取 | FACT-35 | `approval_engine.py` + `kernel.py:_consume_pre_approved` |
| SQL 构建模式 | FACT-45 | `kernel_query_state.py` vs `query_builder.py` |
| 去重参数不匹配 | FACT-37 | `background_worker.py` vs `kernel_query_state.py:_query_notifications` |

### 死代码与休眠组件

| 类别 | 内容 | FACT | 行数估算 |
|------|------|------|----------|
| 死事件类型 | BELIEF_FORMED, AgentSpawned, AgentTerminated | FACT-38/39 | ~20 |
| 空查询路径 | _APPLICATION_EVENT_TYPES 空 frozenset | FACT-40 | ~30 |
| 废弃函数 | estimate_tokens(), log_activity() | FACT-41/42 | ~20 |
| 未使用类 | RecallRanker | FACT-44 | ~35 |
| 遗留适配器 | legacy_event_adapter.py | FACT-43 | ~190 |
| 休眠组件 | ExecutionContextProvider, CapabilityContextProvider | FACT-36 | ~400 (保留不删) |
| 遗留表 | patterns, schedules (DDL) | FACT-38 | ~30 |

---

## PR 计划

---

## PR-01: 清理死事件类型与废弃代码

**Type**: CLEANUP
**Budget Impact**: 死代码预算 (0/7 cleaned)
**Depends On**: 无
**Estimated Lines Changed**: +0 / -65
**Constitution Trace**: P1, P8, I-002
**ROADMAP Trace**: Milestone 2 (v0.3.1)

### Files to DELETE (无，仅在文件内删除)

无整文件删除。

### Files to MODIFY

- `backend/app/core/runtime/kernel/constants.py:L35,L113` — 删除 `EVENT_BELIEF_FORMED` 和 `AGGREGATE_PATTERN`
- `backend/app/core/runtime/kernel/constants.py:L19-L20` — 删除 `EVENT_AGENT_SPAWNED` 和 `EVENT_AGENT_TERMINATED`
- `backend/app/core/runtime/kernel/constants.py:L146-L151` — 从 `MEMORY_INDEX_EVENT_TYPES` 中移除 `EVENT_BELIEF_FORMED`
- `backend/app/core/runtime/legacy_event_adapter.py:L49` — 删除 `_APPLICATION_EVENT_TYPES` 空 frozenset 及相关代码路径
- `backend/app/context_runtime.py:L43-L49` — 删除 `estimate_tokens()` 废弃函数，移除 `FragmentResult.__post_init__` 中的调用
- `backend/app/core/agents/user_profile.py:L93-L130` — 删除 `RecallRanker` 类及全局单例

### Rollback Plan
- `git revert` 此 commit
- 回滚后：废弃常量重新出现，但无运行时影响（原代码已不使用它们）
- 风险：LOW — 所有删除项均经过 Truth Audit 确认无调用者

### Risk Analysis
| 维度 | 等级 | 说明 |
|------|------|------|
| 破坏性变更 | NONE | 纯删除，无 API 变化 |
| 测试覆盖 | LOW | 删除的代码无对应测试 |
| 回滚难度 | TRIVIAL | `git revert` 即回滚 |
| 团队影响 | NONE | 不改变任何接口 |
| 预算风险 | SAFE | 仅减少，不增加 |

---

## PR-02: 清理遗留 DDL 表定义

**Type**: CLEANUP
**Budget Impact**: APP_STORAGE 表 (9/11 → 7/11)，遗留表 (3→0)
**Depends On**: PR-01
**Estimated Lines Changed**: +0 / -35
**Constitution Trace**: P8, I-002
**ROADMAP Trace**: Milestone 2 (v0.3.1)

### Files to MODIFY

- `backend/app/store/schema_ddl.py:L189` — 删除 `patterns` 表 DDL
- `backend/app/store/schema_ddl.py` — 删除 `schedules` 表 DDL（如果存在）
- `backend/alembic/versions/v02_projection_tables.py:L86` — 如引用 patterns/schedules，需确认不需要迁移

### Rollback Plan
- `git revert` 此 commit
- 回滚后：遗留表定义恢复，但运行时仍不使用
- 风险：LOW — 两表均无活跃数据路径

### Risk Analysis
| 维度 | 等级 | 说明 |
|------|------|------|
| 破坏性变更 | LOW | 如果数据库中存在旧数据，DROP TABLE 会丢失历史。建议仅删除 DDL，不执行 DROP |
| 测试覆盖 | LOW | 无需专门测试 |
| 回滚难度 | TRIVIAL | `git revert` |
| 团队影响 | NONE | — |
| 预算风险 | SAFE | — |

---

## PR-03: 修复 BackgroundWorker 通知去重失效

**Type**: REFACTOR
**Budget Impact**: 功能 bug (1/1 fixed)
**Depends On**: PR-01
**Estimated Lines Changed**: +15 / -5
**Constitution Trace**: I-005, P3
**ROADMAP Trace**: Milestone 3 (v0.3.2)
**Truth Audit Trace**: FACT-37

### Files to MODIFY

- `backend/app/core/runtime/kernel/kernel_query_state.py:L287-L329` — 在 `_query_notifications()` 中添加 `related_id` 和 `notification_type` 过滤参数处理
- `backend/app/core/runtime/background_worker.py:L82-L87` — 验证调用参数与修改后的方法签名匹配（无需变更）

### 具体变更

`kernel_query_state.py` 的 `_query_notifications()` 中，在现有 filter keys (`id`, `type`, `title`, `unread_only`, `created_on_date`, `limit`, `order`) 基础上新增：

```python
# 新增过滤键
"related_id": lambda v: ("notification_type = ?", [v]) if v is not None else None,
"notification_type": lambda v: ("notification_type = ?", [v]) if v is not None else None,
```

然后修复 `related_id` 的映射（在 schema 中确认列名）。

### Rollback Plan
- `git revert` + 重新部署即回滚
- 回滚后：通知去重逻辑恢复为"几乎无效"状态
- 风险：LOW — 不改变接口，仅修复内部查询

### Risk Analysis
| 维度 | 等级 | 说明 |
|------|------|------|
| 破坏性变更 | NONE | 内部查询增强，API 不变 |
| 测试覆盖 | MEDIUM | 需新增测试验证去重逻辑 |
| 回滚难度 | TRIVIAL | — |
| 团队影响 | NONE | — |
| 预算风险 | SAFE | — |

---

## PR-04: 统一 Kernel Query 的 WHERE/LIMIT/ORDER 构建

**Type**: REFACTOR
**Budget Impact**: 重复 SQL 构建 (1/1 fixed)
**Depends On**: PR-03
**Estimated Lines Changed**: +30 / -80
**Constitution Trace**: I-001, I-004
**Truth Audit Trace**: FACT-45

### Files to MODIFY

- `backend/app/core/runtime/kernel/kernel_query_state.py` — 重构各 `_query_*` 方法，将手写 WHERE 组装替换为 `query_builder.build_where()` 调用
- `backend/app/core/runtime/kernel/query_builder.py` — (如有必要) 扩展 `build_where()` 以支持更多子句类型

### 具体变更

将 `_query_notifications`, `_query_goals`, `_query_tasks`, `_query_memories` 等方法中的自拼接 WHERE 子句：

```python
# 旧（手写 WHERE）
clauses = []
if id_val:
    clauses.append("id = ?")
    params.append(id_val)
sql = f"WHERE {' AND '.join(clauses)}"

# 新（使用 query_builder）
sql, params = build_where(filters)
```

### Rollback Plan
- `git revert` — 所有查询语义应保持不变
- 回滚后：恢复为手写 SQL 但功能一致
- 风险：MEDIUM — SQL 字符串拼接是常见 bug 源，需充分测试

### Risk Analysis
| 维度 | 等级 | 说明 |
|------|------|------|
| 破坏性变更 | LOW | 纯内部重构，查询语义不变 |
| 测试覆盖 | MEDIUM | 需确认所有查询状态测试通过 |
| 回滚难度 | EASY | `git revert` |
| 团队影响 | LOW | 统一查询模式后降低新贡献者的学习曲线 |
| 预算风险 | SAFE | — |

---

## PR-05: 消除审批双路径读取

**Type**: REFACTOR
**Budget Impact**: 审批概念 (3→3, 暂不合并 — 合并见 M4)
**Depends On**: PR-04
**Estimated Lines Changed**: +10 / -8
**Constitution Trace**: B-002, I-001
**Truth Audit Trace**: FACT-35

### Files to MODIFY

- `backend/app/core/runtime/kernel/kernel.py:L567` — 将 `_consume_pre_approved()` 中的 `self.query_state("approvals", id=approval_id)` 替换为通过 `ApprovalEngine` 的共享查询方法

可选方案（选其一）：
- **方案 A**: 在 `ApprovalEngine` 中新增 `get_by_id(approval_id)` 方法，`Kernel._consume_pre_approved` 通过此方法读取
- **方案 B**: 将审批读取逻辑抽取到 `approval_reader.py` 共享模块，两者均引用

推荐方案 A（改动最小）。

### Rollback Plan
- `git revert`
- 回滚后：双路径恢复独立
- 风险：LOW — 纯读取路径统一，不改变写入

### Risk Analysis
| 维度 | 等级 | 说明 |
|------|------|------|
| 破坏性变更 | NONE | 内部重构 |
| 测试覆盖 | MEDIUM | 审批流相关测试需验证 |
| 回滚难度 | TRIVIAL | — |
| 团队影响 | NONE | — |
| 预算风险 | SAFE | — |

---

## PR-06: 统一运行时调度 — RuntimeLoop (ROADMAP M1)

**Type**: BUDGET (合并)
**Budget Impact**: 调度引擎 (3→1), 后台循环 (3→1)
**Depends On**: PR-05
**Estimated Lines Changed**: +200 / -350
**Constitution Trace**: B-005, I-007 (Scheduler recovery)
**ROADMAP Trace**: Milestone 1 (v0.3.0)

### Files to CREATE

- `backend/app/core/runtime/runtime_loop.py` — 统一调度引擎，按优先级处理 WorkItem（即时执行 > 定时执行 > 后台清理）

### Files to MODIFY

- `backend/app/core/runtime/agent_scheduler.py` — 保留 WorkItem 状态机逻辑，移除独立 tick 循环
- `backend/app/main.py:L172-L268` — 启动序列中用 `runtime_loop.start()` 替换 `background_worker.start()` + `init_scheduler()`
- `backend/app/core/runtime/runtime_container.py` — 注册 `runtime_loop`
- `backend/app/core/runtime/cron_registry.py` — 将 8 个 cron 计划迁移到 RuntimeLoop 内部管理

### Files to DELETE

- `backend/app/core/runtime/timer_engine.py` — 计时扫描合并到 RuntimeLoop (FACT-12)
- `backend/app/core/runtime/background_worker.py` — 后台轮询合并到 RuntimeLoop (FACT-13)
- `backend/app/core/runtime/legacy_event_adapter.py` — 删除 window 到期 (FACT-C2-01: ACTIVE-deprecated, 3 个调用者需先迁移)
- `backend/app/api/goals.py:L11` — 移除 `from app.core.runtime.legacy_event_adapter import goal_legacy_events`，改为直接读 event_log
- `backend/app/core/agents/world_model.py:L11` — 移除 `from app.core.runtime.legacy_event_adapter import to_legacy_dict`，改为直接构造

### Files to MODIFY (级联)

- `backend/app/core/runtime/read_ports.py:L16` — 移除 `from app.core.runtime.legacy_event_adapter import recent_legacy_events`
- `backend/app/core/runtime/read_ports.py:L68-L73` — 将 `query_recent_legacy_events()` 改为直接读 event_log

### 设计要点

RuntimeLoop 单一 tick（建议 100ms），内部按优先级调度：

```
RuntimeLoop._tick():
  1. Process due timers (原 TimerEngine._check_and_fire)
  2. Process WorkItems queue (原 Scheduler._tick, max 8 concurrent)
  3. Process background tasks (原 BackgroundWorker._poll_loop)
  4. Process recovery (原 Scheduler._recover, 仅在启动时)
```

- 保持 I-007 (Scheduler recovery)：`_recover()` 逻辑移植到 RuntimeLoop
- 保持 TimerFired 事件发射：8 个 cron 计划不变
- 保持 BackgroundWorker 的停滞目标检测和审批过期逻辑

### Rollback Plan
- `git revert` + 恢复旧启动序列
- 回滚后：恢复为三个独立循环
- 风险：HIGH — 运行时核心变更，需充分集成测试

### Risk Analysis
| 维度 | 等级 | 说明 |
|------|------|------|
| 破坏性变更 | MEDIUM | 改变后台循环的 tick 频率和顺序 |
| 测试覆盖 | LOW | 当前缺少 RuntimeLoop 的测试 |
| 回滚难度 | MEDIUM | 涉及 5+ 文件的级联变更 |
| 团队影响 | MEDIUM | 开发人员需理解新的调度模型 |
| 预算风险 | SAFE | 合并不超预算 |

---

## PR-07: 合并能力治理 — CapabilityGovernance (ROADMAP M4)

**Type**: BUDGET (合并)
**Budget Impact**: 审批系统 (3→1)
**Depends On**: PR-06
**Estimated Lines Changed**: +150 / -250
**Constitution Trace**: B-002, I-003
**ROADMAP Trace**: Milestone 4 (v0.4.0)

### Files to CREATE

- `backend/app/core/runtime/capability_governance.py` — 统一的能力治理模块

### Files to MODIFY

- `backend/app/core/runtime/kernel/kernel.py:L601-L800` — `invoke_capability()` 改为调用 `capability_governance.decide_and_execute()`
- `backend/app/core/runtime/runtime_container.py` — 替换 capability_gateway/capability_policy/approval_engine 为 capability_governance

### Files to DELETE

- `backend/app/core/runtime/capability_decision.py` → 合并到 capability_governance (FACT-11)
- `backend/app/core/runtime/capability_policy.py` → 合并到 capability_governance (FACT-32)
- `backend/app/core/runtime/approval_engine.py` → 合并到 capability_governance (FACT-35)

### 设计要点

```
CapabilityGovernance:
  - decide(principal, tool_name, args, execution_context) → Decision
    - Gate 1: policy_forbidden()
    - Gate 2: principal_has_grant()  
    - Gate 3: consume_pre_approved()
    - Gate 4: risk_assess() → request_approval()
  - list_pending_approvals()  # 原 ApprovalEngine
  - seed_policy()             # 原 CapabilityPolicy
```

单入口替代原三个模块的分散调用。

### Rollback Plan
- `git revert` + 恢复三个旧模块
- 回滚后：Gate 逻辑无变化（纯整合，不重写裁决逻辑）
- 风险：MEDIUM — 影响所有工具调用

### Risk Analysis
| 维度 | 等级 | 说明 |
|------|------|------|
| 破坏性变更 | LOW | 外部接口为 Kernel ABI，不变 |
| 测试覆盖 | MEDIUM | 审批相关测试约 5 个文件需更新导入 |
| 回滚难度 | MEDIUM | 涉及 3 个文件删除 + 3 个文件修改 |
| 团队影响 | LOW | 简化概念（3→1），降低理解成本 |
| 预算风险 | SAFE | 合并不超预算 |

---

## PR-08: 全局单例消除（ROADMAP M5）

**Type**: REFACTOR
**Budget Impact**: 全局单例 (5+→0)
**Depends On**: PR-07
**Estimated Lines Changed**: +30 / -60
**Constitution Trace**: B-001
**ROADMAP Trace**: Milestone 5 (v0.5.0)

### Files to MODIFY

- `backend/app/core/runtime/kernel_instance.py` — 删除，Kernel 仅通过 RuntimeContainer 访问
- `backend/app/core/runtime/agent_bus.py:L190-L191` — 移除全局 `agent_bus` 单例
- `backend/app/core/runtime/taint.py:L91` — 移除全局 `taint_registry` 单例
- `backend/app/core/runtime/capability_policy.py` (已删除于 PR-07)
- `backend/app/core/harness/mcp_hub.py:L738` — 移除全局 `mcp_hub` 单例
- `backend/app/core/runtime/runtime_container.py` — 确保所有访问点通过 RuntimeContainer

### 级联修改

所有 `from x import singleton` 模式改为 `container = RuntimeContainer(); container.x`。

关键调用点：
- `backend/app/api/chat.py:L101` — `ensure_agent(kernel)` → `container.kernel`
- `backend/app/core/agents/brain.py` — 工具调用访问
- `backend/app/core/agents/mvp/bypass_handlers.py` — handler 注册

### Rollback Plan
- `git revert` 恢复单例模式
- 回滚后：架构回退但功能不变
- 风险：MEDIUM — 全局导入模式变更影响面广

### Risk Analysis
| 维度 | 等级 | 说明 |
|------|------|------|
| 破坏性变更 | LOW | 功能不变，仅改变访问路径 |
| 测试覆盖 | MEDIUM | 108 个测试文件的导入可能受影响 |
| 回滚难度 | MEDIUM | 大量文件的导入语句需恢复 |
| 团队影响 | MEDIUM | 开发人员需适应新的访问模式 |
| 预算风险 | SAFE | — |

---

## PR-09: Context Fragment 精简 (ROADMAP M6)

**Type**: BUDGET (合并)
**Budget Impact**: Context Fragment (13→≤8)
**Depends On**: PR-08
**Estimated Lines Changed**: +60 / -200
**Constitution Trace**: B-008
**ROADMAP Trace**: Milestone 6 (v0.6.0)

### Files to CREATE

- `backend/app/fragments/universal/timeline.py` — 合并 actions + events → TimelineFragment
- `backend/app/fragments/integration_fragment.py` — 合并 calendar + mail → IntegrationFragment

### Files to MODIFY

- `backend/app/fragments/register.py` — 注册新的合并 Fragment，移除旧的 4 个
- `backend/app/core/runtime/governance/fragment_selector.py` — 更新 tier 分类

### Files to DELETE

- `backend/app/fragments/universal/actions.py` → 合并到 timeline.py
- `backend/app/fragments/universal/events.py` → 合并到 timeline.py
- `backend/app/fragments/calendar/__init__.py` → 合并到 integration_fragment.py
- `backend/app/fragments/mail/__init__.py` → 合并到 integration_fragment.py

### 设计要点

TimelineFragment 收集用户的最近操作和事件，按时间线排列。IntegrationFragment 按需加载日历和邮件信息。

### Rollback Plan
- `git revert` + 恢复旧 fragment 注册
- 回滚后：恢复 13 个独立 fragment
- 风险：LOW — 仅改变 prompt 编译的输入，不影响核心运行时

### Risk Analysis
| 维度 | 等级 | 说明 |
|------|------|------|
| 破坏性变更 | LOW | System prompt 内容可能轻微变化 |
| 测试覆盖 | MEDIUM | Fragment 相关测试需更新 |
| 回滚难度 | EASY | — |
| 团队影响 | LOW | — |
| 预算风险 | SAFE | — |

---

## PR-10: 工具预算合规 — 低频工具外部化 (ROADMAP M7)

**Type**: BUDGET
**Budget Impact**: Builtin 工具类别 (13→≤8), Builtin 工具总数 (37→≤20)
**Depends On**: PR-07 (CapabilityGovernance 合并)
**Estimated Lines Changed**: +30 / -300
**Constitution Trace**: B-003, P4
**ROADMAP Trace**: Milestone 7 (v0.7.0)

### Files to CREATE

- `backend/mcp_external_configs/computer_use.json` — computer_use MCP 外部配置
- `backend/mcp_external_configs/voice.json` — voice MCP 外部配置
- `backend/mcp_external_configs/clipboard_ocr.json` — clipboard_ocr MCP 外部配置

### Files to MODIFY

- `backend/app/core/harness/mcp_hub.py` — 移除 4 类工具的 `_register_*` 调用，合并 browser → web

### Files to DELETE

- `backend/app/core/harness/builtin_tools/computer_use.py`
- `backend/app/core/harness/builtin_tools/voice.py`
- `backend/app/core/harness/builtin_tools/clipboard_ocr.py`
- `backend/app/core/harness/builtin_tools/browser.py` → 合并到 web 类别

### 类别变化

| 删除/合并 | 工具数 | 目标状态 |
|-----------|--------|----------|
| clipboard_ocr → External MCP | 2 | 不再内置 |
| computer_use → External MCP | 7 | 不再内置 |
| voice → External MCP | 2 | 不再内置 |
| browser 合并到 web | 2 → 0 | web 类别工具数: 2→4 |
| **总计** | **37→22, 13→9** | **仍需 1 类别，但接近目标** |

### Rollback Plan
- `git revert` + 恢复本地工具注册
- 回滚后：工具恢复内置，但功能不变
- 风险：MEDIUM — 用户需在配置中显式启用外部 MCP 服务器

### Risk Analysis
| 维度 | 等级 | 说明 |
|------|------|------|
| 破坏性变更 | HIGH | 用户依赖的工具从内置变为外部 MCP，需配置更改 |
| 测试覆盖 | LOW | 对应工具测试需迁移到外部测试或删除 |
| 回滚难度 | MEDIUM | 涉及文件删除和 MCP 配置创建 |
| 团队影响 | LOW | — |
| 预算风险 | WARN | 类别数降至 9，未达 ≤8 目标。需找额外 1 类别合并。 |

---

## PR-11: UserProfile 事件溯源化 (ADR-2026-006 决议)

**Type**: IMPL
**Budget Impact**: GOVERNED 表 (14→15), APP_STORAGE (11→10)
**Depends On**: PR-01
**Estimated Lines Changed**: +100 / -40
**Constitution Trace**: P3, I-001, ADR-2026-006
**ROADMAP Trace**: Milestone 8 (v0.8.0)

### Files to CREATE

- (无新文件 — 在现有 projector 中新增)

### Files to MODIFY

- `backend/app/core/agents/user_profile.py` — 将 `UserProfile` 的直写 SQLite 替换为 `kernel.emit_event("ProfileUpdated", ...)`
- `backend/app/core/runtime/kernel/projectors_core.py` — 新增 `@projector("ProfileUpdated")` 投影器，注册 `_OWNED_TABLES["user_profile"]`
- `backend/app/api/memory.py:L136-L192` — `/api/memory/portrait` 改用 `kernel.query_state("user_profile")` 读取
- `backend/app/store/table_registry.py` — 将 `user_profile` 从 APP_STORAGE 移到 GOVERNED

### 设计要点

事件类型设计：
- `ProfileUpdated(category, key, value)` — 单字段更新
- `ProfileBulkUpdated(category, values: dict)` — 批量更新

投影器保持当前的数据结构不变（preferences, values, relationships, health, finance, career）。

### Rollback Plan
- `git revert` 恢复直写 SQLite
- 回滚后：UserProfile 功能不变，但丢失审计能力
- 风险：MEDIUM — 改变存储范式，需数据迁移

### Risk Analysis
| 维度 | 等级 | 说明 |
|------|------|------|
| 破坏性变更 | MEDIUM | 现有 `user_profile` 数据需迁移到事件流 |
| 测试覆盖 | LOW | 需新增 UserProfile 事件溯源测试 |
| 回滚难度 | MEDIUM | 需回滚表分类和写入路径 |
| 团队影响 | LOW | — |
| 预算风险 | WARN | GOVERNED 表 +1 (14→15)，虽未超 ≤12 目标但方向相反 |

---

## PR-12: 测试补全与 CI 验证增强 (VERIFY)

**Type**: VERIFY
**Budget Impact**: 测试覆盖率 (目标 ≥84% runtime, ≥70% API)
**Depends On**: PR-06, PR-07, PR-10, PR-11
**Estimated Lines Changed**: +400 / -0 (新增测试)
**Constitution Trace**: All Invariants (I-001 ~ I-007)

### Files to CREATE

- `backend/tests/runtime/test_runtime_loop.py` — RuntimeLoop 单元测试
- `backend/tests/runtime/test_capability_governance.py` — CapabilityGovernance 合并后测试
- `backend/tests/runtime/test_user_profile_events.py` — UserProfile 事件溯源测试
- `backend/tests/integration/test_notification_dedup.py` — 通知去重正确性验证

### Files to MODIFY

- `backend/tests/runtime/test_agent_scheduler.py` — 更新调度器测试适配 RuntimeLoop
- `backend/tests/runtime/test_capability_decision.py` — 更新为 CapabilityGovernance
- `backend/tests/runtime/test_approval_engine.py` — 合并到 test_capability_governance
- `backend/tests/runtime/test_capability_policy.py` — 合并到 test_capability_governance
- `backend/tests/runtime/test_background_worker.py` — 迁移到 RuntimeLoop 测试
- `backend/tests/runtime/test_timer_engine.py` — 迁移到 RuntimeLoop 测试
- `backend/tests/runtime/test_notification_bridge.py` — 适配
- `backend/tests/integration/test_approval_flow.py` — 适配 CapabilityGovernance

### Rollback Plan
- 测试文件与对应实现 PR 同步回滚
- 回滚后：测试恢复到各 PR 前状态

### Risk Analysis
| 维度 | 等级 | 说明 |
|------|------|------|
| 破坏性变更 | NONE | 纯测试 |
| 测试覆盖 | LOW → HIGH | 目标覆盖率达标 |
| 回滚难度 | EASY | 删除新测试文件 |
| 团队影响 | NONE | — |
| 预算风险 | SAFE | — |

---

## 依赖图

```
CLEANUP-01 (死代码) ──┬──> REFACTOR-03 (通知去重)
                       │        │
CLEANUP-02 (遗留DDL)  ─┘        ├──> REFACTOR-04 (统一SQL)──> REFACTOR-05 (审批双路径)
                                │                                    │
IMPL-11 (UserProfile) ──────────┘                                    │
                                                                     │
                    ┌────────────────────────────────────────────────┘
                    │
                    └──> BUDGET-06 (RuntimeLoop) ──> BUDGET-07 (CapabilityGovernance)
                                                        │
                    ┌───────────────────────────────────┘
                    │
                    └──> REFACTOR-08 (单例消除) ──> BUDGET-09 (Fragment精简)
                                                        │
                                                        └──> BUDGET-10 (工具外部化)
                                                                │
                                                                └──> VERIFY-12 (测试补全)
```

---

## 总体执行计划

| Phase | PR 编号 | 类型 | Lines Changed | 预计工时 | 风险 |
|-------|---------|------|---------------|----------|------|
| 1: Cleanup | PR-01, PR-02 | CLEANUP | +0 / -100 | 2h | LOW |
| 2: Fix & Refactor | PR-03, PR-04, PR-05, PR-11 | REFACTOR + IMPL | +155 / -133 | 8h | MEDIUM |
| 3: Budget Merge | PR-06, PR-07 | BUDGET | +350 / -600 | 16h | HIGH |
| 4: Singleton & Fragment | PR-08, PR-09 | REFACTOR + BUDGET | +90 / -260 | 8h | MEDIUM |
| 5: Tool Externalize | PR-10 | BUDGET | +30 / -300 | 4h | HIGH |
| 6: Verify | PR-12 | VERIFY | +400 / -0 | 8h | LOW |

| 总计 | 12 PRs | — | **+1025 / -1393** | **46h** | — |

### 净代码行变化: -368 行

---

## 执行建议

### 优先级顺序

1. **立即执行 (本周)**: PR-01, PR-02 (死代码清理，无风险，立即减少代码负担)
2. **短期执行 (下周)**: PR-03 (通知去重 bug fix，高优先级), PR-04 (统一查询), PR-05 (消除双路径)
3. **中期执行 (本月)**: PR-06 (RuntimeLoop), PR-07 (CapabilityGovernance) — 需充分测试
4. **长期执行 (下月)**: PR-08 ~ PR-11 — 依赖前置 PR 完成
5. **最后执行**: PR-12 (测试补全，在所有变更稳定后)

### 风险缓解

- PR-06 (RuntimeLoop) 需要最多的集成测试。建议在合并前运行所有 108 个现有测试 + 新增测试
- PR-10 (工具外部化) 有破坏性变更。建议在 v0.7.0 发布前提供迁移指南给用户
- PR-07 (CapabilityGovernance) 影响所有工具调用的授权路径。每个 Gate 需单独验证

---

## 门禁验证

- [x] 每个 PR 都有对应的 Constitution Invariant 追溯
- [x] 每个 PR 都检查了 Budget Cap
- [x] 每个 PR 都有回滚计划
- [x] 零个文档文件被修改（仅输出 IMPLEMENTATION_PLAN.md）
- [x] 零行代码被执行（仅输出计划）
- [x] PR 依赖图无循环依赖
