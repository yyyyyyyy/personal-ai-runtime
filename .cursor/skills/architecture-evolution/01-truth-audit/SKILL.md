---
name: architecture-evolution/01-truth-audit
description: Analyze repository implementation ONLY. Extract system truth — runtime architecture, execution flow, memory system, tool system, governance system, duplicated systems, dead code, dormant components. Outputs FACTS with EVIDENCE and CONFIDENCE. No recommendations, no design, no roadmap. Use as the first stage of the Architecture Evolution cycle.
---

# 01 — Truth Audit

## 核心职责

**唯一职责**: 从代码仓库中提取系统实现的客观事实。

本 Skill 只做一件事：阅读代码，输出事实。

## 硬约束

- **禁止推荐**: 不提出任何改进建议
- **禁止设计**: 不设计新架构或新系统
- **禁止路线图**: 不规划未来工作
- **禁止修改**: 不修改任何文件
- **输出只包含事实**: 不包含任何主观判断

## 输入

本 Skill 不需要参数。支持两种模式：

### 模式 A: 全量审计（首轮 / cycle_count=0）
扫描整个仓库，建立完整 FACT 基线。

### 模式 B: 增量审计（cycle_count ≥ 1，上一轮存在 TRUTH_AUDIT）
当存在上一轮 TRUTH_AUDIT 且代码 diff 较小时使用，避免全量重扫的 churn：

1. 读取上一轮 TRUTH_AUDIT 的 `Commit SHA` 作为 baseline
2. `git diff <baseline>..HEAD --name-only -- backend/app/` 确定变更文件集
3. **只对变更文件所属子系统**重新提取 FACTs（diff-scoped）
4. **必须先消化**上一轮 `VERIFICATION_REPORT.md` 的 "FACT Corrections" 节——纠正的 FACT 要重新审计并给出正确结论，不得重复误判
5. 未变更的子系统：在报告中标注 "UNCHANGED since cycle N"，不重复全文
6. 输出头部标注 `Scope: Incremental (diff <baseline>..<HEAD>)`

增量模式的 FACT 仍须满足全部证据强度规则与质量门禁。

## 执行流程

### 步骤 1: 代码仓库扫描

扫描以下目录结构以建立全局视图：

```
backend/
  app/
    core/
      runtime/       # 运行时核心
      memory/        # 内存系统
      tools/         # 工具系统
      governance/    # 治理系统
    api/             # API 层
    models/          # 数据模型
  tests/             # 测试
docs/
  architecture/      # 架构文档
  engineering/       # 工程文档
  product/           # 产品文档
  reference/         # 参考文档
```

### 步骤 2: 提取系统事实

对每个子系统，提取以下维度的客观事实：

#### 2.1 运行时架构 (Runtime Architecture)

- 入口点列表 (文件路径 + 行号)
- 模块依赖图 (import 关系)
- 类继承层次 (class hierarchy)
- 中间件/拦截器链
- 事件总线/消息传递路径

#### 2.2 执行流 (Execution Flow)

- 请求生命周期 (从入口到响应的完整调用链)
- 异步任务调度机制
- 错误传播路径
- 关键路径上的条件分支

#### 2.3 内存系统 (Memory System)

- 缓存实现位置与策略
- 会话管理机制
- 状态持久化方式
- 临时数据生命周期

#### 2.4 工具系统 (Tool System)

- 已注册工具清单
- 工具发现/加载机制
- 工具执行沙箱
- 工具间通信协议

#### 2.5 治理系统 (Governance System)

- 权限检查点位置
- 审计日志记录点
- 配置管理来源
- 特性开关实现

#### 2.6 冗余检测

- 功能重复的模块/类
- 相同逻辑的多处实现
- 废弃但未删除的代码路径

#### 2.7 死代码检测

- 未被调用的函数/类
- 不可达的代码分支
- 导入但未使用的模块

#### 2.8 休眠组件

- 已定义但未注册的组件
- 条件编译下永远为 false 的代码块
- 测试中引用但未在生产代码中使用的接口

### 步骤 3: 输出格式

输出必须严格遵循以下格式：

```markdown
# Truth Audit Report

## Audit Metadata
- **Timestamp**: YYYY-MM-DD HH:MM:SS UTC
- **Repository**: <repo_name>
- **Commit SHA**: <HEAD commit>
- **Working Tree**: CLEAN | DIRTY (<N modified, M untracked>)  ← 必须先跑 `git status` 确认
- **Scope**: Full repository scan

> ⚠️ 若 Working Tree 为 DIRTY，审计基准是工作树而非该 commit。Commit SHA 仅供参考，不得声称审计针对某个干净 commit。

---

## FACT: <事实标题>

**EVIDENCE**: <证据描述，包含文件路径和行号>

**CONFIDENCE**: HIGH | MEDIUM | LOW

**RATIONALE**: <置信度判断依据>

---
```

### 输出条目类型

每个条目必须是以下类型之一：

| 类型 | 说明 |
|------|------|
| `RUNTIME_ARCHITECTURE` | 运行时架构事实 |
| `EXECUTION_FLOW` | 执行流事实 |
| `MEMORY_SYSTEM` | 内存系统事实 |
| `TOOL_SYSTEM` | 工具系统事实 |
| `GOVERNANCE_SYSTEM` | 治理系统事实 |
| `DUPLICATION` | 重复代码事实 |
| `DEAD_CODE` | 死代码事实 |
| `DORMANT_COMPONENT` | 休眠组件事实 |

## 输出文件

输出写入 `docs/engineering/TRUTH_AUDIT.md`。

## 证据强度规则（CRITICAL — 防止误判传播到下游阶段）

某些 FACT 类型若证据不足，会被 Stage 02 写入宪法/ROADMAP、被 Stage 03 计划删除，造成连锁错误。以下类型有**强制证据要求**：

| FACT 类型 | 强制证据 | 不满足时的处理 |
|------|----------|---------------|
| `DEAD_CODE`（未调用） | 必须附 **全仓库调用点 grep 结果**，证明生产代码 0 调用者（测试调用需单独标注） | 不得标 DEAD_CODE；降级为 MEDIUM/LOW 并注明"未验证调用者" |
| `DORMANT_COMPONENT`（已实现未消费） | 必须附 **importer/调用点 grep 结果**，证明生产代码 0 import / 0 调用 | 不得标 DORMANT；标为普通 FACT |
| `DEPRECATED`（声称废弃可删） | 必须区分"声明废弃"与"无调用者"：附调用点 grep。**有活跃调用者的废弃代码不是死代码** | 标为 ACTIVE-DEPRECATED，注明调用者清单 |
| 任何**计数类** FACT（表数、工具数、概念数等） | 必须指向**权威定义源**（如 `table_registry.py`、`register.py`、`_register_*` 方法），不得用 `grep -c <word>` 词频估算 | 标 CONFIDENCE=LOW 并注明估算方法 |

## 质量门禁

输出必须满足：

1. 每条 FACT 都有 EVIDENCE（文件路径+行号）
2. 每条 FACT 都有 CONFIDENCE 标注
3. 所有 HIGH confidence 的 EVIDENCE 可通过文件读取验证
4. 零条建议性语句（不包含 "should"、"recommend"、"consider"、"建议"、"推荐"）
5. 零条设计性语句（不包含架构蓝图、组件定义、接口签名）
6. 每条 DEAD_CODE / DORMANT_COMPONENT / DEPRECATED 都附调用者 grep 证据（见上方证据强度规则）
7. 每条计数类 FACT 都指向权威定义源，不使用词频 grep
8. Audit Metadata 中记录了 Working Tree 的 CLEAN/DIRTY 状态

## 禁止行为清单

- ❌ 输出 "建议将 X 重构为 Y"
- ❌ 输出 "应该添加 Z 模块"
- ❌ 输出 "未来计划支持 W"
- ❌ 输出 "当前的实现不够好"
- ❌ 输出 "更好的做法是"
- ❌ 修改任何源代码或文档
- ❌ 执行任何代码变更
- ❌ 执行任何 git 操作
