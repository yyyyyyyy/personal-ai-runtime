# 开发检查清单

适用于多文件改动、Review 修复、安全加固、提交前自检。**通用步骤在上方；当前仓库的路径与命令见文末「本项目映射」。**

更完整的原则与踩坑模式见 `docs/POSTMORTEM.md`。

---

## 编码小循环

每改完 1–2 个文件立即执行（按栈替换工具名）：

```bash
# 静态检查 + 类型 + 能否编译/构建
<linter> <changed-paths>
<typechecker> <changed-paths>
<compile-or-build-check>
```

不要攒到最后再跑 CI。

---

## 变更公共接口前

1. 全文搜索符号名 / 配置键 / 路由路径  
2. 扩展类型检查范围到已知调用方目录  
3. 跑与改动相关的冒烟测试（`-k` 关键词或单文件）

---

## 功能闭环

- [ ] 新增导出/API/组件 → 确认有调用方  
- [ ] 认证/权限 → HTTP + WebSocket/长连接 + 其他客户端（桌面/CLI）  
- [ ] 中间件或全局配置 → 全量测试  
- [ ] 用户流程 UI → 测到副作用（请求参数、状态变化），不只「能渲染」  
- [ ] 多份策略名单（权限/风险/开关）→ 契约测试仍绿  

---

## 安全相关（通用）

- [ ] 默认绑定与安全默认值：localhost / opt-in 认证 / 破坏性操作需确认  
- [ ] 凭证不出现在 URL query；改握手方式后搜全仓旧写法  
- [ ] 出站 URL、路径访问、命令执行：同类规则集中在一个模块，所有入口复用  
- [ ] Shell：避免 `shell=True` + 白名单；路径：避免字符串前缀判断  
- [ ] 敏感 API 改完后：`rg` README、威胁模型、示例 curl、mock 页、部署模板  
- [ ] 破坏性 API 集成测：成功路径可 mock；真实 wipe/import E2E 用独立脚本  

---

## 测试与 CI

- [ ] 改 fixture / 全局单例 / conftest → 全量测试  
- [ ] 本地门禁与远端 CI 一致（同一 coverage 范围、同一 typecheck 范围）  
- [ ] 扩大 coverage 或 typecheck 范围前，先本地量是否会打红门禁  
- [ ] 剥离模块后：`rg` 旧名于 Makefile、CI、scripts  

---

## 交付前检查清单

- [ ] Lint + typecheck + build 全绿  
- [ ] 全量单元/集成测试（含 CI 要求的 marker / coverage 门槛）  
- [ ] 项目要求的验证脚本（迁移、重建、往返导入等）  
- [ ] 前端测试与类型检查（如适用）  
- [ ] 配置、`.env.example`、用户文档一致  
- [ ] `git status` 无遗漏 `??` 测试或配置文件  
- [ ] 提交信息符合团队规范  

---

## Windows / PowerShell 注意

| 避免 | 改用 |
|------|------|
| `cd foo && cmd` | IDE 的 `working_directory` |
| bash heredoc `<<'EOF'` | `git commit -m "a" -m "b"` 多 `-m` |
| 依赖 shell 内建命令做跨平台测试 | 选用各 OS 都有的可执行文件 |

---

## 本项目映射（personal-ai-os）

> 以下仅服务当前仓库；复制到新项目时删除或替换本节。

### 编码小循环（本仓库）

```bash
cd backend && ruff check app/路径/
cd backend && mypy app/路径/ --ignore-missing-imports
cd backend && python -m compileall app/ -q
cd frontend && npx tsc --noEmit
```

### 关键路径

| 主题 | 位置 |
|------|------|
| 出站 URL 校验 | `backend/app/core/harness/url_safety.py` |
| Shell 执行 | `backend/app/core/harness/mcp_servers/shell.py` |
| 策略真源 | `mcp_hub` 注册名、`capability_policy.json`、`taint.py` |
| 架构/威胁 | `docs/THREAT_MODEL.md`、`docs/RUNTIME_SPEC.md` |

### 安全回归（本仓库）

```bash
cd backend
python -m pytest tests/runtime/test_shell_server.py tests/runtime/test_url_safety.py \
  tests/runtime/test_fetch_ssrf.py tests/runtime/test_browser_ssrf.py \
  tests/runtime/test_filesystem_server.py tests/integration/test_system_api.py -q
python -m pytest tests/runtime/test_taint.py tests/runtime/test_capability_approval.py -q
```

### 提交前 CI 对齐（本仓库）

```bash
cd backend && ruff check app/ && python -m compileall app/ -q
cd backend && mypy app/core/runtime/ app/core/agents/memory_engine.py app/core/agents/memory_extractor.py app/product/ app/api/ app/main.py scripts/ --ignore-missing-imports
cd backend && python -m pytest tests/ -q -m "not live_llm" --cov=app/core/runtime --cov-fail-under=65
cd backend && python scripts/check_boundary.py && python scripts/verify_export_roundtrip.py
cd frontend && npm test && npx tsc --noEmit
```

### 认证改动额外核对

- `frontend/src/hooks/useNotifications.ts`（`Sec-WebSocket-Protocol: auth.<token>`）
- `backend/tests/integration/test_auth.py`
- `desktop/main.js`
- 根目录 `.env` 中 `AUTH_TOKEN` 与 `VITE_AUTH_TOKEN` 一致
