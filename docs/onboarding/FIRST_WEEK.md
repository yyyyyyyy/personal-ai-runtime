# 新人 Onboarding — 第一周指南

目标：让你从"克隆仓库"到"能独立修 bug"用不超过 5 天。

## Day 1: 环境跑通

```bash
git clone https://github.com/yyyyyyyy/personal-ai-runtime.git
cd personal-ai-runtime
cp .env.example .env
# 编辑 .env，填写 LLM_API_KEY（推荐 DeepSeek，注册即送额度）
make install && make dev
# 打开 http://localhost:5173
```

验证清单：
- [ ] 前端能加载
- [ ] 发一条消息，AI 能回复
- [ ] `make ci-local` 全绿

如果卡住，看 [FAQ](../README.md#常见问题)。

## Day 2-3: 理解架构（读文档，不写代码）

按顺序读这 4 篇（每篇约 20 分钟）：

1. **[CONSTITUTION.md](../CONSTITUTION.md)** — 项目的架构宪法。P1-P8 原则 + 8 个 Non-Goals。理解"为什么是 Runtime 不是 App"。
2. **[ARCHITECTURE.md](../architecture/ARCHITECTURE.md)** — 系统如何工作。重点看 §1 架构概览 + §3 执行模型（Chat 请求 5 阶段管线）。
3. **[INVARIANTS.md](../engineering/INVARIANTS.md)** — CI 强制的 13 条不变量。每条都有机器验证。
4. **[CURRENT_STATE.md](../engineering/CURRENT_STATE.md)** — 当前架构 KPI（51 个概念、14 张表、26 个工具）。

关键概念速查：
- **Kernel**：唯一写入口。所有状态变更通过 `emit_event()`。
- **Event Log**：不可变、只追加的真相源。扔掉所有投影表，可从它重建。
- **Capability**：AI 调用外部世界的能力。经 4 门授权（policy → grant → pre-approved → risk）。
- **Fragment**：Context 的最小单元。把数据转换成 LLM 能理解的 prompt 片段。

## Day 4-5: 动手改代码

### 找一个好上手的 issue

- 搜 "good first issue" 标签
- 或从 [ROADMAP](../product/ROADMAP.md) 挑一个 Milestone 1-3 的任务

### 改代码的流程

```bash
# 1. 创建分支
git checkout -b fix/my-first-fix

# 2. 改代码（Kernel 边界内的改动要特别小心）

# 3. 跑测试
make ci-local

# 4. 跑架构守卫（如果改了 Kernel/Projector）
make boundary rebuild-verify export-roundtrip-verify

# 5. 提交（用 commit hook 规范）
git add -A && .cursor/skills/git-commit/commit.sh "fix: 描述你的改动"
git push
```

### 常见陷阱

| 陷阱 | 解决 |
|------|------|
| `ModuleNotFoundError: No module named 'app'` | 必须在 `backend/` 目录下启动 uvicorn |
| CI 报 `boundary guard failed` | 你在 User Space 直接写了 GOVERNED 表。改走 `kernel.emit_event()` |
| CI 报 `projection provenance failed` | 投影行没有对应的事件。检查 projector 是否被调用 |
| 测试串扰（单跑通过、全量跑失败） | 用 `runtime.reset()` 隔离状态 |

## 架构速查图

```
用户消息 → POST /api/chat → emit ChatRequested
  → Scheduler 入队 WorkItem → ChatHandler
    → ContextPipeline 编译 system prompt
    → Brain 调 LLM → 工具调用经 CapabilityGateway 授权
    → emit ChatCompleted → SSE 推送给前端
```

## 需要帮助

- 架构问题：读 [CONSTITUTION.md](../CONSTITUTION.md) 的原则部分
- 代码问题：用 `/docs` 看 OpenAPI 文档
- 测试问题：看 `backend/tests/conftest.py` 的 fixture
