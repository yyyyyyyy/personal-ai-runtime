# 配置参考

所有配置通过 `.env` 文件管理。

## 快速开始

```bash
cp .env.example .env
# 编辑 .env，至少设置 LLM_API_KEY
```

---

## 必填配置

| 变量 | 说明 | 示例 |
|------|------|------|
| `LLM_API_KEY` | 主 LLM API Key | `sk-...`（DeepSeek）或 `sk-...`（OpenAI） |

---

## LLM 配置

| 变量 | 说明 | 默认值 |
|------|------|--------|
| `LLM_BASE_URL` | API 地址 | `https://api.deepseek.com/v1` |
| `LLM_MODEL` | 模型名 | `deepseek-chat` |
| `MAX_TOOL_ITERATIONS` | 单条消息内工具调用轮次上限 | `10` |
| `OPENAI_API_KEY` | OpenAI 备用 API Key | — |
| `ANTHROPIC_API_KEY` | Anthropic 备用 API Key | — |

---

## 本地模型（Ollama）

| 变量 | 说明 | 默认值 |
|------|------|--------|
| `OLLAMA_BASE_URL` | Ollama API 地址 | `http://localhost:11434/v1` |
| `OLLAMA_MODEL` | Ollama 模型名 | `qwen2.5:7b` |
| `MEMORY_EXTRACTOR` | 记忆抽取后端：`ollama` 或 `cloud` | `ollama` |
| `SENSITIVE_OPS_LOCAL` | 敏感操作路由到本地 Ollama | `false` |

---

## 邮件配置（Gmail）

| 变量 | 说明 | 默认值 |
|------|------|--------|
| `EMAIL_USER` | Gmail 地址 | — |
| `EMAIL_PASS` | Gmail 应用专用密码（不是登录密码） | — |
| `EMAIL_IMAP_HOST` | IMAP 服务器 | `imap.gmail.com` |
| `EMAIL_SMTP_HOST` | SMTP 服务器 | `smtp.gmail.com` |
| `EMAIL_SMTP_PORT` | SMTP 端口 | `465` |

获取 App Password：登录 Google 账号 → 开启两步验证 → [应用专用密码](https://myaccount.google.com/apppasswords)。

---

## 服务器配置

| 变量 | 说明 | 默认值 |
|------|------|--------|
| `HOST` | 后端监听地址 | `127.0.0.1` |
| `PORT` | 后端端口 | `8000` |
| `CORS_ORIGINS` | 允许的前端源（逗号分隔） | `http://localhost:5173,http://localhost:5174` |

---

## 认证配置

| 变量 | 说明 | 默认值 |
|------|------|--------|
| `AUTH_TOKEN` | API Bearer 认证 token（留空则关闭） | — |
| `VITE_AUTH_TOKEN` | 前端 token（需与 `AUTH_TOKEN` 一致） | — |

---

## MCP 配置

| 变量 | 说明 | 默认值 |
|------|------|--------|
| `MCP_EXTERNAL_ENABLED` | 是否加载外部 MCP 工具 | `true` |
| `MCP_SERVERS_ENABLED` | 启用的外部 MCP server（`*` = 全部） | `*` |
| `MCP_CONFIG_PATH` | MCP 配置文件路径 | 仓库默认 |

### 外部 MCP 凭证

| 变量 | 对应的 MCP Server |
|------|-------------------|
| `BRAVE_API_KEY` | Brave Search |
| `CONTEXT7_API_KEY` | Context7 |
| `GITHUB_PERSONAL_ACCESS_TOKEN` | GitHub |
| `TAVILY_API_KEY` | Tavily Search |
| `NOTION_TOKEN` | Notion |

---

## 存储路径

| 变量 | 说明 | 默认值 |
|------|------|--------|
| `DATA_DIR` | 数据根目录 | `backend/data/` |
| `SQLITE_PATH` | SQLite 数据库路径 | `backend/data/personal_ai.db` |
| `VECTOR_DIR` | ChromaDB 向量存储路径 | `backend/data/vectors/` |

---

## 文件系统配置

| 变量 | 说明 | 默认值 |
|------|------|--------|
| `FILESYSTEM_ALLOWED_DIRS` | 允许访问的目录（逗号分隔） | 项目根目录 + 家目录 |
| `FILESYSTEM_PROTECTED_PATHS` | 额外保护路径（追加到默认） | — |

---

## 配置优先级

1. `.env` 文件（主要）
2. 环境变量（覆盖 `.env`）
3. 代码默认值

---

*更多信息见 [.env.example](../../.env.example)（含所有可用变量的完整注释）。*
