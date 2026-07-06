# Personal AI Runtime — 文档

本目录是 Personal AI Runtime 的官方文档，所有内容均依据当前代码库（`backend/`、`frontend/`、`desktop/`、根目录脚本）撰写。文档与代码不一致时，以代码为准。

当前版本：`0.2.0`（[`backend/app/version.py`](../backend/app/version.py)）。

---

## 阅读路径

**首次接触本项目**：从 [01-overview/project-overview.md](01-overview/project-overview.md) 开始，了解项目形态与三大子系统，然后阅读 [01-overview/architecture.md](01-overview/architecture.md) 理解整体架构。

**理解核心设计**：阅读 [02-concepts/](02-concepts/) 下的四份概念文档——事件溯源、Kernel 边界、能力治理、上下文管线是理解所有后续文档的基础。

**深入子系统实现**：根据关注点选择 [03-subsystems/](03-subsystems/) 中的对应文档。

**做工程操作**（开发、测试、部署、扩展）：直接查阅 [05-engineering/](05-engineering/) 下的工程指南。

**查 API / 命令清单**：使用 [06-reference/](06-reference/) 下的参考表。

---

## 文档索引

### 01 · 概览

| 文档 | 内容 |
|---|---|
| [project-overview.md](01-overview/project-overview.md) | 项目是什么、为什么存在、整体形态 |
| [architecture.md](01-overview/architecture.md) | 三层架构、事件溯源 + Kernel 边界、组件关系图 |

### 02 · 核心概念

| 文档 | 内容 |
|---|---|
| [runtime-algebra.md](02-concepts/runtime-algebra.md) | ⭐ 五原语（Event/State/Capability/Work/Context）、三条判据、概念压缩契约 |
| [event-sourcing.md](02-concepts/event-sourcing.md) | `event_log` → projectors → 投影表的数据流 |
| [kernel-boundary.md](02-concepts/kernel-boundary.md) | GOVERNED vs APP_STORAGE 表分类与边界守卫机制 |
| [capability-governance.md](02-concepts/capability-governance.md) | 3-gate 授权、taint 追踪、Principal、execution_scope |
| [context-pipeline.md](02-concepts/context-pipeline.md) | Fragment 注册 → Selector 选择 → Assembler 组装 |

### 03 · 子系统

| 文档 | 内容 |
|---|---|
| [backend-core.md](03-subsystems/backend-core.md) | Brain 推理循环、工具派发、记忆引擎、RuntimeLoop、Scheduler |
| [backend-api.md](03-subsystems/backend-api.md) | 16 个 router、约 70 个端点、SSE、WebSocket |
| [frontend.md](03-subsystems/frontend.md) | React 路由、API client 分层、状态管理、hooks |
| [desktop.md](03-subsystems/desktop.md) | Electron 进程模型、后端 spawn、IPC、托盘与快捷键 |
| [mcp-harness.md](03-subsystems/mcp-harness.md) | 内建工具注册、外部 MCP 网格生命周期 |

### 04 · 数据与配置

| 文档 | 内容 |
|---|---|
| [data-model.md](04-data/data-model.md) | 14 张 governed 表 + 10 张 app 表、ChromaDB collections |
| [configuration.md](04-data/configuration.md) | `.env`、`config.py`、运行时 DB 配置、能力策略 JSON、MCP 配置 |

### 05 · 工程

| 文档 | 内容 |
|---|---|
| [development.md](05-engineering/development.md) | 环境搭建、`make dev`、本地开发循环 |
| [testing.md](05-engineering/testing.md) | pytest 矩阵、16 个 verify 脚本、Playwright e2e、desktop smoke |
| [ci-cd.md](05-engineering/ci-cd.md) | GitHub Actions、Conventional Commits 钩子、Dependabot |
| [deployment.md](05-engineering/deployment.md) | Docker Compose、Dockerfile、桌面端打包、数据卷 |
| [security.md](05-engineering/security.md) | 认证、限流、SSRF 防护、出口审计、加密导出 |
| [extending.md](05-engineering/extending.md) | 投影器、事件 handler、Fragment、MCP、工具、通道、Provider 扩展点 |

### 06 · 参考

| 文档 | 内容 |
|---|---|
| [api-endpoints.md](06-reference/api-endpoints.md) | 全端点签名表（方法 / 路径 / 请求 / 响应 / 副作用） |
| [makefile-targets.md](06-reference/makefile-targets.md) | 全 Makefile 目标清单与说明 |

---

## 文档约定

- 所有事实陈述均可追溯到具体 `file:line` 引用。
- 代码中无法确认的内容标记为「代码库中证据不足」，不做推测。
- 代码标识符、文件路径、命令、配置项保留英文原文；叙述性文字使用中文。
- 文档之间通过相对链接交叉引用，避免内容重复。
- 部分实现未启用（如 `workflows` router）会显式标注当前状态。
