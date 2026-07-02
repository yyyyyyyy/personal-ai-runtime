# ARCHITECTURE GOVERNANCE

> 本文档是 Personal AI Runtime 项目的**永久治理手册**。
> 它定义项目如何演进，不是项目当前是什么。
> 它是未来贡献者和 AI Coding Agent 都必须遵守的操作系统。
>
> **原则：文档引领实现。预算约束演进。删除优于重构。**

---

## 1. 开发生命周期

项目的演进遵循一个严格的五阶段循环。每个阶段有明确的输入、输出和触发条件。

### 1.1 Truth Audit（真相审计）

**触发条件**：每个里程碑完成后（至少）；或在实现演进开始前。

**目标**：以实现为唯一真相源，审计文档是否与实现一致。

**输入**：
- 全部实现代码（`backend/app/`、`frontend/src/`）
- 所有 CI 脚本输出
- 当前所有活跃文档

**动作**：
1. 读取实现代码，提取真实的运行时概念、模块边界、执行流
2. 计算架构 KPI（概念计数、重复系统、休眠能力等——见 §4）
3. 与 `CURRENT_STATE.md` 逐项比对，标记漂移
4. 与 `ARCHITECTURE_BUDGET.md` 逐项比对，标记预算违规
5. 与 `INVARIANTS.md` 逐项比对，标记不再被 CI 验证的不变量
6. 输出审计报告

**输出**：Truth Audit Report（Markdown），包含：
- 概念清单（实际 vs 记录）
- 预算违规列表
- 文档漂移标记
- 建议：是否需要进入 CONSTITUTION UPDATE

**规则**：
- 审计阶段**不修改**任何文档
- 审计阶段**不修改**任何代码
- 审计报告是只读的输入

### 1.2 Architecture Constitution Update（宪法更新）

**触发条件**：Truth Audit 发现原则性偏差，或项目方向需要调整。

**目标**：重新定义架构宪法，使文档成为下一实现周期的指引。

**允许的操作**：
- 更新 `CONSTITUTION.md`（原则、边界、Non-Goals）
- 更新 `ARCHITECTURE_BUDGET.md`（预算目标）
- 更新 `ROADMAP.md`（里程碑规划）
- 更新 `INVARIANTS.md`（新不变量定义）

**禁止的操作**：
- 修改任何代码
- 修改 `CURRENT_STATE.md`
- 修改 `CHANGELOG.md`

**规则**：
- 新增 Core Principle 需要显式理由和版本号变更
- 调整预算目标需要成本-收益分析
- 路线调整必须回溯到宪法原则

### 1.3 Implementation Evolution（实现演进）

**触发条件**：宪法和目标已更新，准备实现。

**目标**：按 ROADMAP 里程碑拆分任务，逐单元实现。

**执行方式**：通过 `.cursor/skills/dev-loop/SKILL.md` 定义的执行单元。

**每个执行单元必须**：
1. Gate 1: 目标合规（任务属于当前 ROADMAP 里程碑）
2. 实现 + 测试（最多 3 次修复迭代）
3. Gate 2: 架构合规（不破坏 INVARIANTS 中任何 Tier 1 规则）
4. Gate 3: PR 待审（永不自动 merge）

**规则**：
- 实现不得绕过治理边界（CONSTITUTION NG7）
- 新增概念必须同步删除或降级一个概念（预算约束）
- 实现不修改文档（文档同步在下一阶段完成）

### 1.4 Reality Verification（真实验证）

**触发条件**：每个实现里程碑完成后。

**目标**：机械验证实现符合所有架构约束。

**动作**：
1. CI 全量运行（`make ci-local`）
2. 不变量守卫脚本全绿（`make boundary execution-ownership projection-provenance rebuild-verify export-roundtrip-verify vector-consistency-verify`）
3. 覆盖率达标（Runtime ≥ 84%, API ≥ 50%，目标 70%）
4. 预算合规检查（扫描概念计数、工具数、表数）

**输出**：Verification Report，包含：
- CI 全部步骤通过/失败
- 预算合规状态
- 新引入的概念计数

**规则**：
- 任何失败 = 不能进入下一阶段
- 修复 CI 失败属于本阶段，不属于新实现单元
- 覆盖率下降必须修复或提供书面理由

### 1.5 Reality Sync（现实同步）

**触发条件**：真实验证全部通过后。

**目标**：将已验证的实现事实同步到文档层。

**允许的操作**：
- 更新 `CURRENT_STATE.md`（仅可测量事实）
- 更新 `ARCHITECTURE.md`（若架构发生实质性变化）
- 更新 `CHANGELOG.md`
- 更新 `reference/API.md`（若 API 变化）
- 更新 `reference/CONFIGURATION.md`（若配置变化）

**禁止的操作**：
- 修改 `CONSTITUTION.md`
- 修改 `ARCHITECTURE_BUDGET.md`
- 修改 `ROADMAP.md`
- 修改 `INVARIANTS.md`

**规则**：
- `CURRENT_STATE.md` 只包含可测量事实，无意见、无计划
- 与上次审计的漂移必须在此阶段消除

### 1.6 生命周期循环

```
TRUTH AUDIT (定期，至少每里程碑一次)
    │
    ├── 存在原则性偏差 → CONSTITUTION UPDATE
    │                        │
    └── 无原则性偏差 ────────┤
                             ▼
                    IMPLEMENTATION EVOLUTION
                    (dev-loop 执行单元)
                             │
                             ▼
                    REALITY VERIFICATION
                    (CI + 不变量守卫)
                             │
                             ├── 失败 → 修复后回到 VERIFICATION
                             │
                             ▼ 成功
                    REALITY SYNC
                    (文档同步)
                             │
                             ▼
                    NEXT CYCLE → TRUTH AUDIT
```

**关键约束：**
- 实现从不以文档为事实源。文档是蓝图，实现是真相。
- 验证从不相信人眼。一切通过 CI 脚本机械验证。
- 同步只改可测量事实。宪法永远不被"现实"修改——只有"审计"可以触发宪法修订。

---

## 2. PR 治理

项目使用五种固定 PR 类型。每种类型有明确的权限边界。

### 2.1 Architecture Constitution PR

**代码**：`type: constitution`

**目的**：修改项目的原则、预算、路线或不可违反规则。

**允许修改的文件**：
- `docs/CONSTITUTION.md`
- `docs/ARCHITECTURE_GOVERNANCE.md`
- `docs/ARCHITECTURE_BUDGET.md`
- `docs/product/ROADMAP.md`
- `docs/engineering/INVARIANTS.md`

**禁止修改的文件**：
- 任何 `backend/app/` 下的代码
- 任何 `frontend/src/` 下的代码
- `docs/engineering/CURRENT_STATE.md`
- `CHANGELOG.md`

**必需的输入**：
- Truth Audit Report（触发宪法更新的审计报告）
- 变更的理由文档（为什么改这条原则/预算）
- 影响分析（哪些里程碑、预算、不变量受影响）

**必需的输出**：
- 变更后的文档
- 变更日志（在 PR 描述中，非 CHANGELOG.md）

**合并条件**：
- 至少一位人类审查者批准
- 审查者确认为总体架构方向负责的人
- 所有依赖文档的不一致性已解决

**审查标准**：
- 新原则是否与现有原则冲突？
- 预算调整是否有充分理由？
- 路线变更是否回溯到宪法原则？
- Non-Goals 是否被偷偷绕过？

**回滚策略**：
- 宪法变更是显式的版本号升级
- 回滚 = 回到上一个宪法版本 + 重新审计

### 2.2 Implementation Evolution PR

**代码**：`type: impl`

**目的**：实现 ROADMAP 中定义的一个执行单元。

**允许修改的文件**：
- `backend/app/` 下的代码
- `frontend/src/` 下的代码
- `backend/tests/` 下的测试
- `backend/requirements.txt`（新增依赖）
- `.cursor/skills/dev-loop/traces/`（执行跟踪）

**禁止修改的文件**：
- 所有 `docs/` 下的文档（ROADMAP, CONSTITUTION, ARCHITECTURE 等）
- `CHANGELOG.md`
- `.cursor/skills/dev-loop/SKILL.md`
- `.cursor/skills/dev-loop/execution_policy.json`

**必需的输入**：
- ROADMAP 里程碑引用
- 受影响模块清单

**必需的输出**：
- 实现代码 + 测试
- 执行跟踪（trace JSON）
- 变更摘要

**合并条件**：
- CI 全部通过（所有不变量守卫脚本）
- Runtime 覆盖率 ≥ 84%，API 覆盖率 ≥ 50%（目标 70%）
- Mypy 类型检查通过
- 不违反 INVARIANTS Tier 1 任何规则

**审查标准**：
- 代码是否正确地通过 Kernel ABI？
- 是否新增了未经授权的 GOVERNED 表直写？
- 是否新增了概念但未删除或降级等价概念？
- 测试是否充分覆盖？

### 2.3 Reality Verification PR

**代码**：`type: verify`

**目的**：新增或更新 CI 检查、不变量守卫脚本、测试基础设施。

**允许修改的文件**：
- `backend/scripts/` 下的验证脚本
- `.github/workflows/ci.yml`
- `Makefile`（验证相关的 target）
- `backend/pyproject.toml`（测试/工具配置）
- `backend/tests/`（仅测试基础设施，非产品测试）

**禁止修改的文件**：
- 产品代码（`backend/app/`、`frontend/src/`）

**必需的输入**：
- 为什么需要新的验证（引用 INVARIANTS 或预算）
- 对应的 INVARIANTS 条目（若新增验证）

**合并条件**：
- 新验证脚本自身通过
- 不破坏现有 CI

### 2.4 Reality Sync PR

**代码**：`type: sync`

**目的**：将已验证的实现状态同步到文档层。

**允许修改的文件**：
- `docs/engineering/CURRENT_STATE.md`
- `docs/architecture/ARCHITECTURE.md`
- `CHANGELOG.md`
- `docs/reference/API.md`
- `docs/reference/CONFIGURATION.md`
- `docs/guides/USER_GUIDE.md`

**禁止修改的文件**：
- `docs/CONSTITUTION.md`
- `docs/ARCHITECTURE_BUDGET.md`
- `docs/ARCHITECTURE_GOVERNANCE.md`
- `docs/product/ROADMAP.md`
- `docs/engineering/INVARIANTS.md`
- 任何代码文件

**必需的输入**：
- Verification Report（验证全部通过）
- 上一个 Reality Sync 后的变更清单

**合并条件**：
- CURRENT_STATE 中所有数据可从代码/CI 机械获取
- 无主观评价

### 2.5 Release PR

**代码**：`type: release`

**目的**：版本发布。

**允许修改的文件**：
- `backend/app/version.py`
- `CHANGELOG.md`
- `docs/engineering/CURRENT_STATE.md`（版本号）

**禁止修改的文件**：
- 所有其他文件

**必需的输入**：
- 里程碑完成确认（所有该里程碑的 `impl` PR 已合并）
- Reality Sync 已完成

---

## 3. 文档治理

### 3.1 文档所有权

| 文档 | 所有方 | 允许修改的 PR 类型 | 禁止修改的 PR 类型 | 依赖 | 被谁消费 |
|---|---|---|---|---|---|
| `CONSTITUTION.md` | 首席架构师 | `constitution` | 所有其他类型 | 无（是最顶层文档） | ROADMAP, ARCHITECTURE, INVARIANTS, BUDGET |
| `ARCHITECTURE_GOVERNANCE.md` | 工程经理 | `constitution` | 所有其他类型 | CONSTITUTION | 全部贡献者, AI Agent |
| `ARCHITECTURE_BUDGET.md` | 首席架构师 | `constitution` | 所有其他类型 | CONSTITUTION | ROADMAP, CURRENT_STATE, dev-loop |
| `ROADMAP.md` | 技术项目经理 | `constitution` | 所有其他类型 | CONSTITUTION, BUDGET | dev-loop, 贡献者 |
| `INVARIANTS.md` | CI/CD 所有方 | `constitution` | 所有其他类型 | CONSTITUTION | CI, dev-loop |
| `ARCHITECTURE.md` | 技术文档所有方 | `constitution`, `sync` | `impl`, `verify`, `release` | CONSTITUTION | 贡献者 |
| `CURRENT_STATE.md` | CI/CD 所有方 | `sync`, `release` | `constitution`, `impl`, `verify` | ARCHITECTURE | 全部贡献者 |
| `MANIFESTO.md` | 产品经理 | `constitution` | 所有其他类型 | CONSTITUTION | 贡献者 |
| `API.md` | 后端所有方 | `sync` | 所有其他类型 | 代码 | 贡献者 |
| `CONFIGURATION.md` | 后端所有方 | `sync` | 所有其他类型 | 代码 | 贡献者 |
| `DEVELOPER_GUIDE.md` | 技术文档所有方 | `sync` | `constitution`, `impl` | ARCHITECTURE | 新贡献者 |
| `USER_GUIDE.md` | 产品经理 | `sync` | 所有其他类型 | 产品状态 | 用户 |

### 3.2 文档职责

每个文档**有且仅有一个职责**。不重复，不交叉。

| 文档 | 为什么存在 | 谁读 | 谁更新 | 何时更新 | 何时绝不能改 |
|---|---|---|---|---|---|
| `CONSTITUTION.md` | 定义项目身份和架构原则 | 全部贡献者 | Constitution PR | 原则性方向调整时 | 实现演进期间 |
| `ARCHITECTURE_GOVERNANCE.md` | 定义项目如何演进 | 全部贡献者, AI Agent | Constitution PR | 治理流程调整时 | 实现演进期间 |
| `ARCHITECTURE_BUDGET.md` | 定义概念数量和复杂度约束 | 全部贡献者 | Constitution PR | 预算目标调整时 | 实现演进期间 |
| `ROADMAP.md` | 规划架构演进路线 | dev-loop, 贡献者 | Constitution PR | 里程碑规划调整时 | 实现演进期间 |
| `INVARIANTS.md` | 定义 CI 强制的不违反规则 | CI, dev-loop | Constitution PR | 新增/移除不变量时 | 实现演进期间 |
| `ARCHITECTURE.md` | 解释当前运行时架构 | 贡献者 | Constitution / Sync PR | 架构概念发生变化时 | 不应包含主观评价 |
| `CURRENT_STATE.md` | 提供当前可测量的架构 KPI | 全部贡献者 | Sync PR | 每次 Reality Sync | 不应包含预测、计划、意见 |
| `MANIFESTO.md` | 对外品牌声明 | 外部用户 | Constitution PR | 品牌定位调整时 | 不应包含技术细节 |
| `API.md` | API 参考文档 | 贡献者, 集成者 | Sync PR | API 发生变化时 | 不应包含实现细节 |
| `CONFIGURATION.md` | 配置项参考 | 用户, 贡献者 | Sync PR | 配置项变化时 | 不应包含架构决策 |
| `DEVELOPER_GUIDE.md` | 新贡献者上手指南 | 新贡献者 | Sync PR | 架构变化影响开发流程时 | 不应包含架构决策 |
| `USER_GUIDE.md` | 终端用户使用手册 | 用户 | Sync PR | 产品功能变化时 | 不应包含技术细节 |

---

## 4. 架构 KPI 仪表盘

以下 KPI 构成项目的永久架构健康仪表盘。每个 KPI 有明确的定义、测量方式、阈值和更新频率。

### 4.1 运行时概念计数

| 属性 | 值 |
|---|---|
| **定义** | 在 `CURRENT_STATE.md` 中列为 Core 或 Supporting 的运行时概念总数 |
| **测量** | 审计阶段扫描所有 Python 模块，提取公开类和函数 |
| **当前** | 47 |
| **目标** | ≤ 25 (v1.0) |
| **警告阈值** | > 30 (接近目标 2 倍) |
| **临界阈值** | > 50 (概念爆炸) |
| **更新频率** | 每个里程碑审计 |

### 4.2 Core 概念计数

| 属性 | 值 |
|---|---|
| **定义** | 列为 Core 的、"理解 Runtime 必须知道"的概念数 |
| **测量** | `CURRENT_STATE.md` 中 Core 分类条目数 |
| **当前** | 15 |
| **目标** | ≤ 10 (v1.0) |
| **警告阈值** | > 15 |
| **临界阈值** | > 20 |
| **更新频率** | 每个里程碑审计 |

### 4.3 调度引擎计数

| 属性 | 值 |
|---|---|
| **定义** | 独立的、周期性执行任务的引擎数（Scheduler, TimerEngine, BackgroundWorker 等） |
| **测量** | 审计阶段统计独立的事件循环 / tick 循环 |
| **当前** | 3 |
| **目标** | 1 (统一 RuntimeLoop) |
| **警告阈值** | > 3 |
| **临界阈值** | > 4 |
| **更新频率** | 每个里程碑审计 |

### 4.4 审批系统计数

| 属性 | 值 |
|---|---|
| **定义** | 能力授权相关的独立概念（CapabilityGateway, CapabilityPolicy, ApprovalEngine） |
| **测量** | 审计阶段统计授权/审批相关模块 |
| **当前** | 3 |
| **目标** | 1 (合并为 CapabilityGovernance) |
| **警告阈值** | > 3 |
| **临界阈值** | > 4 |
| **更新频率** | 每个里程碑审计 |

### 4.5 全局单例计数

| 属性 | 值 |
|---|---|
| **定义** | 模块级别的单例对象（非 RuntimeContainer 管理） |
| **测量** | 审计阶段扫描 `kernel_instance`, 模块级 `= Class()` 赋值 |
| **当前** | 5+ |
| **目标** | 0 (全部通过 RuntimeContainer) |
| **警告阈值** | > 5 |
| **临界阈值** | > 8 |
| **更新频率** | 每个里程碑审计 |

### 4.6 后台循环计数

| 属性 | 值 |
|---|---|
| **定义** | 独立的后台循环（tick / poll / scan）的数量 |
| **测量** | 审计阶段统计 `while True` 或 `asyncio.create_task` 的循环 |
| **当前** | 3 |
| **目标** | 1 |
| **警告阈值** | > 3 |
| **临界阈值** | > 4 |
| **更新频率** | 每个里程碑审计 |

### 4.7 重复系统计数

| 属性 | 值 |
|---|---|
| **定义** | 解决同一问题但有不同实现路径的系统数（如 `events` vs `event_log`） |
| **测量** | 审计阶段识别功能重叠的表、类、或流程 |
| **当前** | 3 |
| **目标** | 0 |
| **警告阈值** | > 2 |
| **临界阈值** | > 4 |
| **更新频率** | 每个里程碑审计 |

### 4.8 休眠/已弃用能力

| 属性 | 值 |
|---|---|
| **定义** | 标记为 Deprecated、Dormant、或 Experimental（且未升级到 Supporting）的概念数 |
| **测量** | `CURRENT_STATE.md` 中非 Active 状态的条目 |
| **当前** | 4 (LegacyEventAdapter + 3 Experimental) |
| **目标** | 0 |
| **警告阈值** | > 3 |
| **临界阈值** | > 6 |
| **更新频率** | 每个里程碑审计 |

### 4.9 Context Fragment 计数

| 属性 | 值 |
|---|---|
| **定义** | Context Pipeline 中注册的 Fragment 实现数 |
| **测量** | 审计阶段扫描 Fragment 注册文件 |
| **当前** | 13 |
| **目标** | ≤ 8 |
| **警告阈值** | > 13 |
| **临界阈值** | > 16 |
| **更新频率** | 每个里程碑审计 |

### 4.10 Builtin 工具类别计数

| 属性 | 值 |
|---|---|
| **定义** | `builtin_tools/` 下的独立工具类别数 |
| **测量** | CI 中的 `verify MCP tools` 步骤 |
| **当前** | 12 |
| **目标** | ≤ 8 |
| **警告阈值** | > 12 |
| **临界阈值** | > 15 |
| **更新频率** | 每个实现 PR（CI 自动检查） |

### 4.11 API 路由组计数

| 属性 | 值 |
|---|---|
| **定义** | FastAPI 注册的独立 Router 数量 |
| **测量** | CI 中的 `verify API routes` 步骤 |
| **当前** | 17 |
| **目标** | ≤ 12 |
| **警告阈值** | > 17 |
| **临界阈值** | > 20 |
| **更新频率** | 每个实现 PR（CI 自动检查） |

### 4.12 GOVERNED 表计数

| 属性 | 值 |
|---|---|
| **定义** | `table_registry.py` 中 `GOVERNED_TABLES` 包含的表数 |
| **测量** | 审计阶段读取 `table_registry.py` |
| **当前** | 14 |
| **目标** | ≤ 12 |
| **警告阈值** | > 14 |
| **临界阈值** | > 16 |
| **更新频率** | 每个里程碑审计 |

### 4.13 APP_STORAGE 表计数

| 属性 | 值 |
|---|---|
| **定义** | `table_registry.py` 中 `APP_STORAGE_TABLES` 包含的表数 |
| **测量** | 审计阶段读取 `table_registry.py` |
| **当前** | 11 |
| **目标** | ≤ 6 |
| **警告阈值** | > 11 |
| **临界阈值** | > 12 |
| **更新频率** | 每个里程碑审计 |

### 4.14 测试覆盖率

| 属性 | 值 |
|---|---|
| **定义** | Runtime 代码和 API 代码的测试覆盖率 |
| **测量** | CI 中的 pytest-cov |
| **目标** | Runtime ≥ 84%, API ≥ 50%（目标 70%） |
| **临界阈值** | Runtime < 84% (CI 硬失败), API < 50% (CI 告警) |
| **更新频率** | 每个实现 PR（CI 自动检查） |

### 4.15 CI 健康

| 属性 | 值 |
|---|---|
| **定义** | 所有 CI 步骤通过的比例 |
| **测量** | 最近一次 CI 运行结果 |
| **目标** | 100% (24/24 steps) |
| **警告阈值** | Miss ≥ 1 step |
| **临界阈值** | Miss ≥ 3 steps |
| **更新频率** | 每个实现 PR |

### 4.16 文档漂移

| 属性 | 值 |
|---|---|
| **定义** | 文档中提到但代码中不存在（或语义不一致）的断言数 |
| **测量** | Truth Audit 阶段的逐个比对 |
| **目标** | 0 |
| **警告阈值** | > 2 |
| **临界阈值** | > 5 |
| **更新频率** | 每个里程碑审计 |

### 4.17 KPI 仪表盘汇总

| KPI | 当前 | 目标 | 警告 | 临界 | 更新频率 |
|---|---|---|---|---|---|
| 运行时概念总数 | 47 | ≤ 25 | > 30 | > 50 | 每里程碑 |
| Core 概念 | 15 | ≤ 10 | > 15 | > 20 | 每里程碑 |
| 调度引擎 | 3 | 1 | > 3 | > 4 | 每里程碑 |
| 审批系统 | 3 | 1 | > 3 | > 4 | 每里程碑 |
| 全局单例 | 5+ | 0 | > 5 | > 8 | 每里程碑 |
| 后台循环 | 3 | 1 | > 3 | > 4 | 每里程碑 |
| 重复系统 | 3 | 0 | > 2 | > 4 | 每里程碑 |
| 休眠能力 | 4 | 0 | > 3 | > 6 | 每里程碑 |
| Context Fragment | 13 | ≤ 8 | > 13 | > 16 | 每里程碑 |
| Builtin 工具类别 | 12 | ≤ 8 | > 12 | > 15 | CI 自动 |
| API 路由组 | 17 | ≤ 12 | > 17 | > 20 | CI 自动 |
| GOVERNED 表 | 14 | ≤ 12 | > 14 | > 16 | 每里程碑 |
| APP_STORAGE 表 | 11 | ≤ 6 | > 11 | > 12 | 每里程碑 |
| Runtime 覆盖率 | 84%+ | ≥ 84% | < 84% | n/a | CI 自动 |
| CI 健康 | 100% | 100% | miss 1 | miss 3+ | 每 PR |
| 文档漂移 | 0 | 0 | > 2 | > 5 | 每里程碑 |

---

## 5. 治理规则

以下规则定义项目的"宪法级"约束。它们优先于任何实现便利。

### 5.1 文档与实现的关系

1. **文档引领实现。** 宪法定方向，架构定约束，实现是对文档的遵循，不是文档是对实现的记录。
2. **实现是真相的最终仲裁者。** 当文档与实现冲突，Truth Audit 决定哪一方需要改变。但改变的方向永远是：如果实现比文档好（更简洁、更一致），文档升级。如果实现偏离了宪法，实现必须回退。
3. **现实从不修改宪法。** CONSTITUTION.md 只由 Constitution PR 修改。Reality Sync 永远不能碰宪法。

### 5.2 预算约束

4. **新增概念 = 删除或降级一个概念。** 运行时概念总数不能增长。任何 `impl` PR 中新增一个 Core 概念，必须同时降级或删除一个现有的 Core 或 Supporting 概念。
5. **新增工具 = 新增一条策略 + 一条污点规则 + 测试。** 每个新内建工具带来安全面增长，必须有对应的策略和测试。
6. **新增 GOVERNED 表 = 新增投影器 + 重建验证 + 列清单。** 每张新 GOVERNED 表增加事件类型的组合爆炸风险。

### 5.3 不可妥协的边界

7. **Agents 永远不能直接访问存储。** 任何绕过 `kernel.emit_event()` 或 `kernel.invoke_capability()` 的对 GOVERNED 表的访问是架构违规。
8. **能力调用必须 fail-closed。** 无法判定授权时，默认拒绝。不存在"暂时允许，以后再限制"的通道。
9. **用户数据必须始终可导出。** 任何破坏数据导出完整性的变更被禁止。
10. **事件日志只追加不修改。** 没有例外。没有"仅此一次"的 UPDATE。

### 5.4 文档一致性

11. **每份文档有且仅有一个职责。** 不允许跨文档重复。发现重复 = 必须合并或删除其一。
12. **CURRENT_STATE.md 只包含可测量事实。** 无主观评价。无未来计划。无历史叙述。
13. **INVARIANTS.md 每条必须有机器的验证方式。** 不允许"人工检查"作为唯一验证手段。

### 5.5 演进规则

14. **不得为功能牺牲边界。** 见 CONSTITUTION NG7。当功能需求与治理边界冲突，治理胜出。
15. **架构演进 = 简化，不是拓展。** ROADMAP 中的每个里程碑必须有预期删除列表。净增长为负是最好的里程碑。
16. **删除 > 重构 > 扩展。** 设计新方案时，首选删除不需要的部分，其次重构为更简洁的形式，最后才考虑增加新东西。

---

## 6. 审查门

每个 PR 合并前必须通过所有适用门。门分为两类：**自动门**（CI 脚本）和**人工门**（审查者确认）。

### 6.1 Architecture Gate（架构合规门）

**适用 PR**：`impl`, `sync`

**自动检查**：
- `check_boundary.py` — 无直写 GOVERNED 表
- `check_execution_ownership.py` — invoke_capability 携带 execution_id
- `check_projection_provenance.py` — 投影可追溯
- `verify_rebuild.py` — 事件日志重建
- `verify_export_roundtrip.py` — 数据导出往返
- `verify_vector_consistency.py` — 向量索引一致

**人工检查**：
- 是否新增了概念但未在 BUDGET 中备案？
- 概念总数是否增长？若增长，同步删除了什么？
- 是否引入了新的依赖方向？

### 6.2 Product Gate（产品合规门）

**适用 PR**：`impl`

**自动检查**：
- Gate 1（dev-loop 步骤 1）：任务属于当前 ROADMAP 里程碑

**人工检查**：
- 变更是否违反任何 Non-Goal？
- 是否引入了平台锁定风险？

### 6.3 Documentation Gate（文档合规门）

**适用 PR**：`impl`, `sync`, `verify`

**自动检查**：
- `impl` PR 不修改 `docs/` 下的宪法文档
- `sync` PR 不修改 `CONSTITUTION.md`、`BUDGET.md`、`ROADMAP.md`、`INVARIANTS.md`

**人工检查**：
- `sync` PR 中的 CURRENT_STATE 更新是否只包含可测量事实？
- 是否有跨文档重复？

### 6.4 Testing Gate（测试合规门）

**适用 PR**：`impl`, `verify`

**自动检查**：
- Runtime 覆盖率 ≥ 84%
- API 覆盖率 ≥ 50%（目标 70%）
- 后端 pytest 全量通过（排除 live_llm）
- 前端 vitest 全量通过
- 前端 Playwright E2E 通过

### 6.5 Runtime Gate（运行时合规门）

**适用 PR**：`impl`

**自动检查**：
- `verify_alembic.py` — schema 迁移正确
- `verify_memory_lifecycle.py` — 记忆生命周期
- `verify_conversation_rebuild.py` — 对话重建
- `verify_goal_rebuild.py` — 目标重建
- `verify_inbox_audit.py` — 收件箱审计
- `verify_egress.py` — LLM 出站审计
- `verify_connector.py` — 连接器验证

### 6.6 Complexity Gate（复杂度门）

**适用 PR**：`impl`, `sync`

**自动检查**：
- Mypy 类型检查通过
- Ruff lint 通过
- TypeScript `tsc --noEmit` 通过

**人工检查**：
- 新增代码是否引入新的循环依赖？
- 新增抽象是否比需要的更复杂？

### 6.7 Budget Gate（预算门）

**适用 PR**：`impl`, `constitution`

**自动检查**：
- 内置工具 ≥ 28（CI MCP tools verify）
- 核心 API 端点负载正常（CI API route verify）

**人工检查**：
- 概念计数是否在预算内？
- 若新增概念，是否同步删除或降级？
- 若修改预算，是否有充分的成本-收益分析？

### 6.8 门汇总

| 门 | `constitution` | `impl` | `verify` | `sync` | `release` |
|---|---|---|---|---|---|
| Architecture Gate | — | CI + 人工 | CI + 人工 | CI + 人工 | — |
| Product Gate | — | 人工 | — | — | — |
| Documentation Gate | 人工 | 自动 | 自动 | 自动 + 人工 | 自动 |
| Testing Gate | — | CI | CI | — | — |
| Runtime Gate | — | CI | — | — | — |
| Complexity Gate | 人工 | CI + 人工 | CI | 人工 | — |
| Budget Gate | 人工 | 人工 | 人工 | 人工 | — |

---

## 7. 成功指标

项目的健康由以下指标衡量，而非功能数或代码行数。

### 7.1 主要指标

| 指标 | 定义 | 测量方式 | 趋势目标 |
|---|---|---|---|
| 概念计数 | 运行时概念的总数 | Truth Audit 扫描 | 持续下降 |
| 删除比例 | 删除的代码行 / 新增的代码行 | Git diff | > 1（删的比写的多） |
| 预算合规率 | 达标 KPI / 总 KPI | KPI 仪表盘 | 100% |
| CI 首次通过率 | 首次 CI 运行全部通过的比例 | CI 统计 | 持续上升 |
| 文档漂移 | 文档与实现不一致的断言数 | Truth Audit 比对 | 0 |
| 休眠能力 | 标记为 Deprecated / Dormant / Experimental 的概念数 | CURRENT_STATE.md | 0 |
| PR 大小 | 单个 PR 修改的文件数和行数 | Git diff | 持续减小 |
| 重复系统 | 功能重叠的系统数 | Truth Audit | 0 |

### 7.2 认知负荷指标

| 指标 | 定义 | 目标 |
|---|---|---|
| 理解架构的时间 | 新贡献者理解核心架构所需的阅读文档量 | ≤ 4 个文档（CONSTITUTION + ARCHITECTURE + BUDGET + GOVERNANCE） |
| 核心概念数 | 理解 Runtime 必须知道的概念 | ≤ 10 |
| 模块依赖图深度 | import 图的直径 | ≤ 5 |
| 全局状态点 | 分散的模块级单例数 | 0 |

### 7.3 质量指标

| 指标 | 定义 | 目标 |
|---|---|---|
| 不变量强制 | Tier 1 不变量 100% 有 CI 自动验证 | 100% |
| 覆盖率 | Runtime ≥ 84%, API ≥ 50%（目标 70%） | 持续上升 |
| CI 完整性 | CI 步骤覆盖所有关键路径 | 不下降 |
| 文档完整性 | 每个文档有明确的单一职责 | 100% |

### 7.4 评估频率

| 频率 | 评估内容 |
|---|---|
| 每个 PR | CI 健康、覆盖率、PR 大小 |
| 每个里程碑 | 概念计数、预算合规、文档漂移、重复系统、休眠能力 |
| 每个宪法修订 | 全部主要指标 + 认知负荷指标 |

---

## 8. 治理文档的演进

本文档（`ARCHITECTURE_GOVERNANCE.md`）是治理系统的元文档。它定义项目如何演进——但它自身也可以演进。

### 8.1 修改规则

- 修改本文档属于 `constitution` PR
- 需要首席架构师批准
- 修改不能降低治理标准（不能删除审查门、不能放宽预算阈值）

### 8.2 版本

| 版本 | 日期 | 变更 |
|---|---|---|
| v1.0 | 2026-06-30 | 初始版本。定义五阶段生命周期、五种 PR 类型、12 个文档的所有权和职责、16 个 KPI、7 个审查门、3 类 16 项成功指标。 |

---

## 附录 A：文档结构全图

```
docs/
├── CONSTITUTION.md                 ← 宪法（Constitution PR 修改）
├── ARCHITECTURE_GOVERNANCE.md      ← 治理（Constitution PR 修改）
├── ARCHITECTURE_BUDGET.md          ← 预算（Constitution PR 修改）
├── architecture/
│   └── ARCHITECTURE.md             ← 架构解释（Constitution/Sync PR 修改）
├── engineering/
│   ├── INVARIANTS.md               ← 不变量（Constitution PR 修改）
│   └── CURRENT_STATE.md            ← 当前状态（仅 Sync PR 修改）
├── product/
│   ├── MANIFESTO.md                ← 品牌声明（Constitution PR 修改）
│   └── ROADMAP.md                  ← 路线图（Constitution PR 修改）
├── reference/
│   ├── API.md                      ← API 参考（Sync PR 修改）
│   └── CONFIGURATION.md            ← 配置参考（Sync PR 修改）
├── guides/
│   ├── DEVELOPER_GUIDE.md          ← 开发者指南（Sync PR 修改）
│   └── USER_GUIDE.md               ← 用户手册（Sync PR 修改）
├── assets/                         ← 截图等静态资源
└── archive/                        ← 已存档的历史文档
```

## 附录 B：关键术语

| 术语 | 定义 |
|---|---|
| Truth Audit | 以实现为唯一真相源，审计文档与实现的一致性 |
| Constitution | 定义项目身份、原则、边界的顶层文档 |
| Budget | 对运行时概念、模块、工具等的数量约束 |
| Gateway | Kernel 对能力调用的四门授权检查 |
| Invariant | CI 强制验证的不可违反规则 |
| Reality Sync | 将已验证的实现事实同步到文档层的阶段 |
| Drift | 文档与实现之间的不一致 |
| Dormant | 已实现但不在活跃使用中的概念或代码 |
