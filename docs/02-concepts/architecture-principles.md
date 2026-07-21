# Architecture Principles

本文档定义 Personal AI Runtime 的架构原则、边界规则与演化纪律。它回答 **What / Why / How**，不预测时间表，不记录审计过程。

相关理论见 [runtime-algebra.md](runtime-algebra.md)；机器强制的不变量见 [runtime-invariants.md](runtime-invariants.md)；表级边界见 [kernel-boundary.md](kernel-boundary.md)。

---

## 1. Runtime 与 Product

### 1.1 定义

| | Runtime | Product |
|---|---|---|
| **回答的问题** | 如何正确执行、审计、恢复 | 为用户完成什么领域工作 |
| **扩展方式** | 组合原语 | 通过 Kernel ABI 使用原语 |
| **领域依赖** | 不依赖邮件/日历等业务语义 | 依赖具体领域 |

**Runtime** 只负责五类机制：

1. **真相** — 不可变事件日志与可重建投影
2. **执行** — 带归属、可恢复的计算调度
3. **能力** — 外部效果的统一治理入口
4. **上下文** — 触发执行的输入快照构造
5. **生命周期** — 时钟、超时、崩溃恢复、瞬时推送（Transport）

**Product** 负责领域策略与用户可见行为：HTTP 适配、inbox/知识库/仪表盘、领域 Fragment、业务 Reaction、产品能力实现等。

### 1.2 边界判据

| 判据 | Runtime | Product |
|---|---|---|
| 是否实现原语机制 | 是 | 否（只调用） |
| 是否绑定具体业务领域 | 否 | 是 |
| 是否经 Kernel ABI 访问 governed 数据 | 自身实现 ABI | 必须经 ABI |
| 典型目录 | `core/runtime/`、Capability 基础设施（`core/harness/` 中的 hub/mesh/安全） | `app/api/`、`app/product/`、`app/fragments/`、领域工具实现 |

### 1.3 边界规则

1. Product **不得**直访 governed 表或 `event_log`（见 [kernel-boundary.md](kernel-boundary.md)）。
2. Product **不得**绕过 `invoke_capability` 执行外部效果。
3. Product **应**通过注册 Capability / Fragment / Handler 扩展，而不是向 Runtime 增加领域概念。
4. Runtime **不应**持续吸收产品策略（例如具体「收件箱积压」规则、用户档案字段语义）。这类逻辑属于 Product。
5. Capability **基础设施**（注册表、网格、URL 安全、执行路由）属于 Runtime；**具体工具实现**（邮件发送、日历写入、Telegram 等）属于 Product，即使当前源码仍可能位于 `core/harness/builtin_tools/`。

### 1.4 层依赖规则（机器强制）

表级 GOLDEN RULE 见 [kernel-boundary.md](kernel-boundary.md)。下列**职责边**由 [`check_layer_deps.py`](../../backend/scripts/check_layer_deps.py) 扫描：

| 规则 | 禁止边 | 说明 |
|---|---|---|
| R1 | `core/runtime` → `app.product` | 机制不得回调领域策略 |
| R2 | `store` → `app.core.runtime` | 存储层不得装配 Runtime |
| R3 | `api` → Runtime 私有名 / 非 ABI 深模块 | HTTP 只碰 Kernel ABI 面 |
| R4 | `product` → Runtime 深模块 | Product 优先 `kernel` / Ports ABI（包名 `read_ports`）/ `constants` / `egress` |

**API / Product 允许的 ABI 面**：

- `kernel_instance`（含 `ensure_runtime_scheduler` / `get_runtime_scheduler` / `get_current_execution_id`）
- **Ports ABI**（包路径仍为 `read_ports`：投影读 + Work/Triggers 命令包装 + SSE/推送桥；历史包名不改以免 churn）
- `kernel.constants`、`runtime_config`（公开 API）、`egress`
- Product 另允许 `from app.core.runtime.kernel import Kernel`（类型提示，不含 `kernel.*` 其它子模块）

已知违规记在脚本 `DEBT_ALLOWLIST`；CI 默认阻断**新增**边。查看清单：

```bash
make layer-deps-inventory   # 或 python -m scripts.check_layer_deps --inventory
```

---

## 2. 概念纪律

### 2.1 Concept Compression（概念压缩）

- 核心概念数应单调下降或零和持平。
- 新增模块 / 事件类型 / Fragment / governed 表 / `query_state` selector，必须在同变更中删除等价旧概念。
- CI 红线见 [runtime-algebra.md §4.4](runtime-algebra.md)；强制脚本为 `check_concept_growth.py`。

### 2.2 Concept Growth（概念增长）的含义

真正的复杂度是概念增长，不是文件体积叙事。下列信号表明边界正在松弛：

- 为同一问题引入第二套平行模型（例如第二套任务表、第二套调度叙事）
- Runtime 目录持续堆积 Product 策略
- 新增 Manager / Service / Framework 层来「整理」已有原语

### 2.3 Boundary Drift（边界漂移）

当目录布局与职责判据不一致时，以**职责判据**为准修正归属，而不是用新抽象掩盖错位。典型漂移：

- 领域工具实现落在 Runtime 树下
- Storage 层反向依赖 Runtime 容器装配
- 模块级可变全局状态游离于 `RuntimeContainer` 之外

---

## 3. Work Model 统一

系统只有一套 WORK 原语，两个 subtype：

| Subtype | 持久化 | 用途 |
|---|---|---|
| 领域 Work | `work_items` | goal / task / action 等用户可见工作 |
| 调度 Work | `handler_executions` | 一次 handler 执行（ScheduledExecution） |

禁止：

- 把领域 Work 与调度 Work 合并为同一张表
- 为后台任务再发明第三套「任务」模型（应收敛为领域 Work）
- 用 Lane 叙事之外的平行「Agent 引擎」描述执行

执行语义见 [execution-model.md](execution-model.md)。

---

## 4. 演化原则

以下原则长期成立，与具体里程碑无关：

1. **Product 持续从 Runtime 分离** — 领域策略与工具实现迁向 Product；Runtime 只保留机制。
2. **Primitive 保持稳定** — 默认不增加原语；新增必须通过吞并测试、持久性测试与概念添加成本（见 [runtime-algebra.md §3](runtime-algebra.md)）。
3. **Runtime 不因功能堆叠而增加概念** — 新能力优先声明/实例化，而不是新目录与新类型。
4. **Work Model 保持统一** — 后台任务、目标、动作都落在 WORK 的既有 subtype 上。
5. **Capability 扩展不引入 Plugin 原语** — 批量注册、manifest、自注册都是 Capability 的装配方式，不是第七原语。
6. **Transport 与 Event 保持正交** — 流式与实时推送不进 `event_log`；完成态事实才持久化。
7. **狗粮证据优先于为洁癖而压缩** — 无日用阻碍时，不为「更干净」而强行删概念。

---

## 5. Forbidden（禁止引入）

下列抽象默认禁止作为新架构层或命名诱饵。需要组织代码时，优先组合现有原语：

| 禁止 | 原因 |
|---|---|
| Framework / Platform / Orchestration Layer | 在 Runtime 与 Product 之间再加一层，掩盖 ABI |
| Manager / Service / Helper / Utils 上帝模块 | 把多个原语职责揉进无边界容器 |
| 第二套 Event / Task / Job 总线 | 破坏 Event / Work 单一模型 |
| 把 Transport 内容写入 event_log | 污染真相层 |
| 静默抬高概念红线 | 掩盖 Concept Growth |
| Adapter 森林 | 用适配器堆叠代替清晰的 Capability 边界 |

**正确方向**：Product 直接调用 Kernel ABI；扩展通过 Capability / Fragment / Handler / Reaction 注册完成。

---

## 6. 与整体架构的关系

三层存储/权限视图（User Space / Kernel Space / App Storage）见 [architecture.md](../01-overview/architecture.md)。

本文的 Runtime / Product 划分是**职责视图**，与表分类正交：Product 代码仍必须遵守 Kernel 边界；Runtime 代码仍不得把 APP_STORAGE 误当成 governed 真相。
