# Runtime Invariants

本文档列出 Personal AI Runtime 必须保持的架构不变量。强度定义：

| 强度 | 含义 | 典型强制方式 |
|---|---|---|
| **Strong** | 违反应被阻断 | CI 静态扫描、DB 触发器、verify 脚本、pytest |
| **Medium** | 运行时强制 | 锁、状态机、ContextVar、断言 |
| **Weak** | 设计约定 | 文档与代码组织；违反会形成债务 |

不变量按原语分组。实现细节以代码与脚本为准。

---

## 1. Event

| ID | 陈述 | 强度 |
|---|---|---|
| INV-E1 | `event_log` 在正常运行期间 append-only；禁止 UPDATE/DELETE（rebuild/restore 为特权路径，受锁保护） | Strong |
| INV-E2 | Event 写入后 payload 与类型字段不可篡改 | Strong |
| INV-E3 | governed State 的写入只能由 `Kernel.emit_event`（及其同步投影）产生 | Strong |
| INV-E4 | governed State 可从 `event_log` 完整重建 | Strong |
| INV-E5 | `emit_event` 中 INSERT `event_log` 与 `projectors.apply` 在同一 SQLite 事务内完成 | Strong |

---

## 2. State

| ID | 陈述 | 强度 |
|---|---|---|
| INV-S1 | governed 投影表仅由 projector 在 Kernel 写路径上更新 | Strong |
| INV-S2 | User Space 不得对 governed 表执行 DML 或 SELECT（`check_boundary.py`） | Strong |
| INV-S3 | ChromaDB memory index 是 State 的派生索引；失败不得回滚已提交事件，应进入可重试修复路径 | Medium |
| INV-S4 | APP_STORAGE 表可直访，但不得被误当作 governed 真相源 | Weak |

---

## 3. Capability

| ID | 陈述 | 强度 |
|---|---|---|
| INV-C1 | 外部工具效果只能经 `Kernel.invoke_capability` | Strong |
| INV-C2 | 调用必须携带 `execution_id`（`check_execution_ownership.py`） | Strong |
| INV-C3 | 授权走 3-gate：forbidden → pre-approved → risk assessment | Strong |
| INV-C4 | 每次调用产生可审计 Capability* 事件 | Strong |
| INV-C5 | 外部摄入类工具污染当前 correlation（taint），后续高风险写入受约束 | Medium |

---

## 4. Work

| ID | 陈述 | 强度 |
|---|---|---|
| INV-W1 | Lane A 每次 handler 调用对应一个 `ScheduledExecution` / `handler_executions` 行 | Strong |
| INV-W2 | 调度状态转换通过 Execution* 事件，而非旁路 UPDATE | Strong |
| INV-W3 | 中断的调度执行可从投影恢复并重试 | Strong |
| INV-W4 | 领域 Work（`work_items`）与调度 Work（`handler_executions`）分离存储、统一原语 | Medium |
| INV-W5 | 后台异步任务应落在统一 Work 模型上，而不是平行任务表 | Weak |

执行车道语义见 [execution-model.md](execution-model.md)。

---

## 5. Context

| ID | 陈述 | 强度 |
|---|---|---|
| INV-X1 | Fragment / Context 组装只读 State（经 read_ports），不得写 governed 数据 | Medium |
| INV-X2 | Fragment 是 Context 的生产函数，不是独立原语 | Weak |
| INV-X3 | 一次 chat turn 的模型输入经统一 Context 管线编译 | Medium |

---

## 6. Transport

| ID | 陈述 | 强度 |
|---|---|---|
| INV-T1 | 流式增量与实时广播不写入 `event_log` | Strong |
| INV-T2 | Transport 失败不得回滚已提交的 governed 写入 | Strong |
| INV-T3 | Transport 丢失可接受；客户端以 State / 完成态 Event 为准重新同步 | Medium |

---

## 7. Boundary & Ownership

| ID | 陈述 | 强度 |
|---|---|---|
| INV-B1 | User Space 经 Kernel ABI 访问 governed 数据（见 [kernel-boundary.md](kernel-boundary.md)） | Strong |
| INV-B2 | 投影行可追溯到对应 `event_log` 事件（provenance 检查） | Strong |
| INV-B3 | Product 扩展通过 ABI / 注册点完成，不向 Runtime 增加领域原语 | Weak |
| INV-B4 | Runtime 依赖装配收敛于 `RuntimeContainer`；避免游离模块级可变单例 | Weak |

---

## 8. Concept Compression

| ID | 陈述 | 强度 |
|---|---|---|
| INV-A1 | 概念指标净增长 ≤ 0（事件类型、runtime 文件、selector、Fragment、governed 表等） | Strong |
| INV-A2 | 抬高 CI 红线必须显式说明被替换的旧概念；禁止静默抬线 | Strong |

详见 [runtime-algebra.md §5](runtime-algebra.md) 与 [architecture-principles.md](architecture-principles.md)。
