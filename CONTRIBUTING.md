# Contributing

感谢你考虑为 Personal AI Runtime 贡献代码、文档或想法。

---

## 行为准则

这个项目遵循两条简单原则：

- 对事不对人。
- 假设善意。

---

## 如何贡献

### 报告 Bug

在 GitHub Issues 中创建 issue。请包含：

- 使用的版本（`git describe --tags`）
- 操作系统和 Python 版本
- 复现步骤
- 相关日志或错误信息

### 提出功能建议

先查看 [ROADMAP](docs/product/ROADMAP.md) 确认是否已在计划中。

建议类 issue 请包含：

- 解决了什么用户问题？
- 你的使用场景是什么？

### 提交代码

1. Fork 并 clone 仓库

```bash
git clone https://github.com/your-username/personal-ai-os.git
cd personal-ai-os
```

2. 设置开发环境

```bash
cp .env.example .env  # 配置 LLM_API_KEY
make install
make dev              # 启动开发服务器
```

3. 创建分支

```bash
git checkout -b feature/your-feature-name
```

4. 在提交前运行本地 CI

```bash
make ci-local
```

这会运行：ruff lint、mypy type check、pytest（所有非 live_llm 测试）、boundary check、ownership check。

5. 提交

使用 [Conventional Commits](https://www.conventionalcommits.org/) 格式：

```
feat: add new tool for calendar sync
fix: resolve approval timeout in background worker
docs: update architecture diagram
refactor: extract ToolDispatcher from Brain
```

6. 创建 Pull Request

PR 标题和描述请说明做了什么、为什么做。

### CI 会检查什么

- `ruff` — 代码风格
- `mypy` — 类型检查
- `pytest` — 单元和集成测试（覆盖率 ≥ 84%）
- `check_boundary.py` — User Space 不直接写治理表
- `check_execution_ownership.py` — 能力调用必须带 `execution_id`
- `check_projection_provenance.py` — 投影行可追溯到 Event Log
- `verify_rebuild.py` — 12 张投影表可确定性重建
- `verify_export_roundtrip.py` — 导出/导入往返无损
- `verify_vector_consistency.py` — SQLite 与 Chroma ID 一致

如果 CI 不通过，PR 不会被合并。

---

## 开发规范

### 架构约束

这个项目的核心约束是不可以绕过 Kernel 直接写治理域数据。

- **GOVERNED_TABLES**（`event_log`、`goals`、`memories`、`approvals` 等 16 张表）：只能通过 `kernel.emit_event()` 写入
- **APP_STORAGE_TABLES**（`inbox_emails`、`llm_calls`、`triggers` 等 9 张表）：允许直写
- 新增业务表必须在 `backend/app/store/table_registry.py` 中显式归类

CI 的 `check_boundary.py` 会扫描所有代码，禁止对 GOVERNED_TABLES 的直接 DML。

### 添加新功能

| 你想添加 | 参考文档 | 关键约束 |
|---------|---------|---------|
| 新 MCP 工具 | [DEVELOPER_GUIDE](docs/guides/DEVELOPER_GUIDE.md) §2 | 必须在 `capability_policy.json` 中分配风险等级 |
| 新 Context Fragment | [DEVELOPER_GUIDE](docs/guides/DEVELOPER_GUIDE.md) §3 | 必须通过 Read Ports 读取数据 |
| 新 Agent Handler | [DEVELOPER_GUIDE](docs/guides/DEVELOPER_GUIDE.md) §4 | 副作用必须绑定 `execution_id` |

### 测试

- 后端测试：`make test-backend`
- 前端测试：`make test-frontend`
- 完整本地 CI：`make ci-local`

---

## 文档贡献

文档在这个项目中与代码同等重要。

- 产品文档在 `docs/product/`
- 使用指南在 `docs/guides/`
- 架构文档在 `docs/architecture/`
- 工程文档在 `docs/engineering/`

文档变更同一 PR 中完成。

---

## 沟通

- Bug 和功能建议：GitHub Issues
- 代码讨论：Pull Request comments

---

## 许可证

本项目采用 MIT 许可证。贡献即同意以 MIT 许可你的代码。
