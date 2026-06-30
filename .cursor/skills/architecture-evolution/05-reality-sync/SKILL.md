---
name: architecture-evolution/05-reality-sync
description: Update ONLY factual documentation — CURRENT_STATE.md, API.md, CHANGELOG.md, CI metrics, coverage, version. MUST NOT modify Constitution, Roadmap, or Budget. Use as the fifth and final stage of the Architecture Evolution cycle, bringing documentation into sync with reality after implementation changes.
---

# 05 — Reality Sync

## 核心职责

**唯一职责**: 将事实性文档与代码实现同步。

本 Skill 只做一件事：更新运行期事实文档。

## 硬约束

- **禁止修改宪法**: 不修改 CONSTITUTION.md
- **禁止修改路线图**: 不修改 ROADMAP.md
- **禁止修改预算**: 不修改 ARCHITECTURE_BUDGET.md
- **禁止修改架构设计**: 不修改 ARCHITECTURE.md
- **只更新事实文档**: 仅修改可观测的、可验证的运行状态文档

## 可修改文件与不可修改文件

### 可修改文件（完整清单）

| 文件 | 操作 | 内容要求 |
|------|------|----------|
| `docs/engineering/CURRENT_STATE.md` | UPDATE | 运行时状态快照 |
| `docs/reference/API.md` | UPDATE | API 端点状态 |
| `CHANGELOG.md` | UPDATE | 版本变更记录 |
| `Makefile` | UPDATE | 构建目标状态 |
| `.github/workflows/ci.yml` | UPDATE | CI 指标 |

### 禁止修改文件

| 文件 | 原因 |
|------|------|
| `docs/CONSTITUTION.md` | 架构宪法 — Stage 02 管辖 |
| `docs/architecture/ARCHITECTURE.md` | 架构设计 — Stage 02 管辖 |
| `docs/ARCHITECTURE_BUDGET.md` | 架构预算 — Stage 02 管辖 |
| `docs/product/ROADMAP.md` | 产品路线图 — Stage 02 管辖 |
| `docs/engineering/CURRENT_STATE_STRUCTURE.md` | 结构定义 — Stage 02 管辖 |
| `docs/engineering/TRUTH_AUDIT.md` | 事实审计 — Stage 01 管辖 |
| `docs/engineering/VERIFICATION_REPORT.md` | 验证报告 — Stage 04 管辖 |
| `docs/engineering/IMPLEMENTATION_PLAN.md` | 实现计划 — Stage 03 管辖 Python |
| `backend/**/*` | 源代码 — Stage 03 管辖 |

## 执行流程

### 权威来源表（CRITICAL — 禁止用词频 grep 估算计数）

计数类指标**必须**从下列权威定义源读取，不得用 `grep -c <word>`（会数到注释/字符串/单词出现次数，产生错误值）：

| 指标 | 权威来源 | 正确读法 |
|------|----------|----------|
| GOVERNED 表数 | `backend/app/store/table_registry.py` → `GOVERNED_TABLES` | 数 frozenset 成员，**含 `event_log`、`projection_checkpoints`** |
| APP_STORAGE 表数 | `table_registry.py` → `APP_STORAGE_TABLES` | 数 frozenset 成员 |
| Builtin 工具类别 | `mcp_hub.py` → `_register_*_tools()` 方法 | 数方法定义 |
| Builtin 工具总数 | `mcp_hub.py` → builtin `register_tool(ToolDef(` 调用 | 排除 `register_mesh_tools` 动态注册 |
| Context Fragment | `fragments/register.py` → fragment 类列表 | 数注册的类，不是 `grep -c Fragment` |
| API 路由组 | `main.py` → `include_router(` 调用 | 数注册调用 |
| Cron 计划 | `cron_registry.py` → `SCHEDULES` | 数列表成员 |

**对账门禁**：CURRENT_STATE.md 中的 GOVERNED/APP_STORAGE/工具/Fragment/路由计数，必须与**同一轮** CONSTITUTION.md、ARCHITECTURE_BUDGET.md、VERIFICATION_REPORT.md 中的对应值**完全一致**。若不一致，先核对权威源找出正确值，再统一——不得让 Stage 05 产物与 Stage 02/04 自相矛盾。

### 步骤 1: CURRENT_STATE.md 同步

更新 `docs/engineering/CURRENT_STATE.md`，遵循 CURRENT_STATE_STRUCTURE.md 定义的结构。

**填充内容**（仅事实数据）:

#### 运行时指标
- 活跃模块数量
- API 端点数量
- 后台任务数量
- 活跃 WebSocket 连接数 (如有)

#### 代码质量指标
- 测试覆盖率百分比
- Linter 违规数量
- 类型检查状态
- 死代码行数

#### 测试指标
- 单元测试数量
- 集成测试数量
- E2E 测试数量
- 测试通过率

#### 部署指标
- 当前版本号
- 最新部署时间戳
- 部署环境状态

**采集方法**:

```bash
# 测试覆盖率
cd backend && python -m pytest --cov=app --cov-report=term 2>/dev/null | tail -5

# 代码行数统计
find backend/app -name "*.py" | xargs wc -l | tail -1

# 模块数量
find backend/app -type d -maxdepth 3 | wc -l

# API 端点数量
rg -r '$1' 'route\("([^"]+)"' backend/app/api/ --no-filename | sort -u | wc -l
```

### 步骤 2: API.md 同步

更新 `docs/reference/API.md`:

**内容要求**:
- 当前所有活跃的 API 端点列表
- 每个端点的 HTTP 方法和路径
- 请求/响应格式
- 认证要求
- 废弃标记 (如有)

**采集方法**: 从代码中提取路由注册和 OpenAPI schema。

**禁止**:
- 添加未实现的端点
- 删除已实现但未文档化的端点（应标记为 MISSING_FROM_DOCS）
- 修改端点行为描述使其与实际不符

### 步骤 3: CHANGELOG.md 同步

更新 `CHANGELOG.md`:

**内容要求**:
- 自上一版本以来的代码变更摘要
- 变更类型（feat/fix/refactor/docs/chore）
- 影响范围

**采集方法（强制）**: 必须先运行 git log/diff，CHANGELOG 条目**只能**基于其真实输出。

```bash
git log --oneline --since="<last_version_date>" -- backend/
git status   # 区分本轮变更 vs 会话前已存在的未跟踪/已修改文件
```

**禁止**:
- 把会话前就已存在的变更（git status 中的 pre-existing 改动）归因为本轮产物
- 写入 git log/diff 中不存在的变更条目
- 声称"已发布"某版本，除非该版本在 `version.py` 中已对应设定

### 步骤 4: CI 指标同步

更新 `.github/workflows/ci.yml` 中的可量化指标（如覆盖率阈值）。

**内容要求**:
- 当前测试覆盖率阈值
- Linter 规则版本
- 依赖版本锁定状态

### 步骤 5: 版本信息同步（硬门禁）

**先读取所有版本来源，检测漂移**：

| 位置 | 字段 | 备注 |
|------|------|------|
| `backend/app/version.py` | `VERSION` | 代码侧权威版本 |
| `backend/app/main.py` | `version=` | FastAPI app 版本 |
| `Makefile` | `VERSION` 变量 | 构建侧 |
| `CHANGELOG.md` | 版本头 | 文档侧 |

**漂移处理规则**：
- 若各来源版本号不一致（例如 `version.py=0.1.0` 但文档=`0.2.0`），**禁止静默选一个值填充**。
- 必须在执行摘要中以 ⚠️ 显式 FLAG 该漂移，并报告所有冲突值与各自位置。
- 仅当能确定唯一正确版本时才统一；否则保持现状并上报，交由人工裁决。版本是发布事实，错填比留空危害更大。

## 输出格式

本 Skill 不产生独立输出文件。它直接修改上述可修改文件。

执行完成后，输出执行摘要：

```markdown
# Reality Sync Execution Summary

## Sync Metadata
- **Timestamp**: YYYY-MM-DD HH:MM:SS UTC
- **Version**: v{X.Y.Z}
- **Commit SHA**: <HEAD commit>

## Files Modified

| File | Changes | Lines Changed |
|------|---------|---------------|
| `docs/engineering/CURRENT_STATE.md` | Field updates | +N / -M |
| `docs/reference/API.md` | Endpoint sync | +N / -M |
| `CHANGELOG.md` | Entry added | +N |
| ... | ... | ... |

## Metrics Snapshot

| Metric | Value |
|--------|-------|
| Test Coverage | X% |
| Active Modules | N |
| API Endpoints | N |
| Test Count | N |
| Dead Code Lines | N |

## Compliance Check

- [ ] No CONSTITUTION.md modified
- [ ] No ROADMAP.md modified
- [ ] No ARCHITECTURE_BUDGET.md modified
- [ ] No ARCHITECTURE.md modified
- [ ] All changes are factual only
```

## 质量门禁

1. 零个被禁止的文件被修改
2. CURRENT_STATE.md 中所有字段遵循 CURRENT_STATE_STRUCTURE.md 定义
3. API.md 中所有端点可在代码中验证
4. CHANGELOG.md 新增条目可在 git log/diff 中验证，且无 pre-existing 改动的错误归因
5. 版本号在所有位置一致；若不一致，已在执行摘要中 FLAG 而非静默填充
6. 所有计数类指标来自权威源（见权威来源表），未使用词频 grep
7. CURRENT_STATE.md 的计数与同一轮 CONSTITUTION/BUDGET/VERIFICATION_REPORT 一致（对账门禁通过）

## 禁止行为清单

- ❌ 修改 CONSTITUTION.md
- ❌ 修改 ROADMAP.md (架构部分或任何部分)
- ❌ 修改 ARCHITECTURE_BUDGET.md
- ❌ 修改 ARCHITECTURE.md
- ❌ 在 CURRENT_STATE.md 中添加主观评价
- ❌ 在 API.md 中添加未实现的端点
- ❌ 在 CHANGELOG.md 中添加不存在的变更
- ❌ 修改源代码 (backend/**/*)
