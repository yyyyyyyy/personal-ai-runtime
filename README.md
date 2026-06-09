# Personal AI OS

一个长期运行的个人 AI 系统——你的第二大脑和执行引擎。不只是聊天，能真正帮你做事：搜索网页、管理文件、追踪目标、生成复盘，越用越懂你。

## 功能概览

- **智能对话**：多轮对话、流式输出、Markdown 渲染、代码高亮
- **工具调用**：AI 自主决定调用哪些工具——查时间、读文件、搜文件、搜网页、抓网页内容
- **目标管理**：自然语言创建目标，自动拆解为行动步骤，Kanban 看板视图，停滞检测与提醒
- **长期记忆**：对话中自动提取偏好和事实，存入本地向量数据库，新对话时自动召回
- **知识库**：导入 Markdown/TXT 文档，自动切片+embedding，支持 RAG 语义问答
- **复盘引擎**：Daily/Weekly/Monthly 三级复盘，聚合事件 → 分析进展 → 生成洞察
- **主动推送**：晨间简报、Deadline 预警，WebSocket 实时通知
- **人生时间线**：按日期浏览所有事件记录，可回溯完整活动历史
- **多 LLM 支持**：DeepSeek（默认）、OpenAI、Claude、Ollama，fallback 自动切换
- **桌面客户端**：Electron 系统托盘、全局快捷键（Alt+Space）、原生通知
- **隐私优先**：全部数据存本地 SQLite + ChromaDB，不上传原始内容

## 技术栈

| 层 | 技术 |
|---|---|
| LLM | DeepSeek API (OpenAI 兼容，128K 上下文) |
| 后端 | Python 3.12 + FastAPI |
| 工具协议 | MCP (Model Context Protocol) |
| Agent 路由 | LLM Function Calling |
| 向量检索 | ChromaDB (本地运行) |
| 结构化存储 | SQLite (WAL 模式) |
| 前端 | React 19 + TailwindCSS 4 + Zustand |
| 桌面壳 | Electron |

## 项目结构

```
personal-ai-os/
├── backend/
│   ├── app/
│   │   ├── main.py            # FastAPI 入口
│   │   ├── config.py          # 配置管理
│   │   ├── api/               # API 路由层
│   │   │   ├── chat.py        # 对话 API (SSE 流式)
│   │   │   ├── goals.py       # 目标 & 行动 API
│   │   │   ├── memory.py      # 记忆 API
│   │   │   ├── knowledge.py   # 知识库 API (RAG)
│   │   │   ├── events.py      # 事件查询 API
│   │   │   ├── reviews.py     # 复盘 API
│   │   │   ├── notifications.py # 通知 API
│   │   │   └── system.py      # 系统 & LLM 提供者 API
│   │   ├── core/              # 核心引擎层
│   │   │   ├── brain.py       # 推理循环 (对话→工具调用→响应)
│   │   │   ├── runtime.py     # (预留) 运行时状态管理
│   │   │   ├── mcp_hub.py     # MCP 工具注册 & 调度中心
│   │   │   ├── llm_router.py  # 多 LLM 提供者路由
│   │   │   ├── conversation.py # 对话管理 (滑动窗口)
│   │   │   ├── context_engine.py # 上下文构建
│   │   │   ├── memory_engine.py  # 记忆提取 & 语义检索
│   │   │   ├── event_recorder.py # 事件记录
│   │   │   ├── review_engine.py  # 复盘引擎
│   │   │   └── scheduler.py      # 定时任务调度
│   │   ├── mcp_servers/       # 内置 MCP Server
│   │   │   ├── filesystem.py  # 安全文件操作
│   │   │   ├── web_search.py  # 网络搜索 (DuckDuckGo)
│   │   │   └── fetch.py       # 网页抓取 & 正文提取
│   │   ├── product/           # 产品功能
│   │   │   ├── morning_brief.py  # 晨间简报
│   │   │   ├── daily_review.py   # 每日复盘触发
│   │   │   ├── weekly_review.py  # 每周复盘触发
│   │   │   ├── monthly_review.py # 每月复盘触发
│   │   │   └── notifications.py  # 通知生成
│   │   └── store/             # 数据存储
│   │       ├── database.py    # SQLite (11 张表)
│   │       └── vector.py      # ChromaDB (2 个 collection)
│   ├── data/                  # 数据目录 (自动创建)
│   └── requirements.txt
├── frontend/
│   └── src/
│       ├── App.tsx            # 根布局 + 导航
│       ├── pages/
│       │   ├── Goals.tsx      # 目标管理页
│       │   └── Timeline.tsx   # 时间线页
│       ├── components/chat/
│       │   ├── ChatView.tsx   # 主对话界面 (SSE)
│       │   ├── MessageItem.tsx # 消息渲染 (Markdown)
│       │   └── ToolCallDisplay.tsx # 工具调用展示
│       ├── api/client.ts      # API 客户端
│       └── stores/            # Zustand 状态管理
├── desktop/                   # Electron 桌面客户端
├── .env                       # 环境配置
└── .env.example
```

## 快速开始

### 环境要求

- Python 3.12+
- Node.js 20+
- DeepSeek API Key（免费注册：[platform.deepseek.com](https://platform.deepseek.com)）

### 1. 配置环境

```bash
cp .env.example .env
```

编辑 `.env`，填入你的 DeepSeek API Key：

```
LLM_API_KEY=sk-your-api-key-here
```

### 2. 启动后端

```bash
cd backend
pip3 install -r requirements.txt
python3 -m uvicorn app.main:app --reload --port 8000
```

### 3. 启动前端

```bash
cd frontend
npm install
npm run dev
```

浏览器打开 `http://localhost:5173`。

### 4. （可选）启动桌面客户端

```bash
cd desktop
npm install
npm start
```

## 可用工具

AI 可在对话中自主调用以下工具：

| 工具 | 说明 |
|------|------|
| `get_current_time` | 获取当前日期时间 |
| `read_file` | 读取文本文件 |
| `write_file` | 写入文件（需用户确认） |
| `list_directory` | 列出目录内容 |
| `search_files` | 按名称搜索文件 |
| `web_search` | 联网搜索（DuckDuckGo） |
| `fetch_url` | 抓取网页并提取正文 |

## API 端点

### 对话
| 方法 | 路径 | 说明 |
|------|------|------|
| POST | `/api/chat/conversations` | 创建对话 |
| GET | `/api/chat/conversations` | 列出对话 |
| GET | `/api/chat/conversations/{id}` | 获取对话详情 |
| PATCH | `/api/chat/conversations/{id}` | 修改标题 |
| DELETE | `/api/chat/conversations/{id}` | 删除对话 |
| POST | `/api/chat/conversations/{id}/messages` | 发送消息（SSE 流式） |
| GET | `/api/chat/conversations/{id}/messages` | 获取历史消息 |

### 目标 & 行动
| 方法 | 路径 | 说明 |
|------|------|------|
| POST | `/api/goals/` | 创建目标 |
| GET | `/api/goals/` | 列出目标 |
| GET | `/api/goals/{id}` | 获取目标详情（含 actions + events） |
| PUT | `/api/goals/{id}` | 更新目标 |
| DELETE | `/api/goals/{id}` | 删除目标 |
| POST | `/api/goals/{id}/actions` | 添加行动 |
| PUT | `/api/goals/{id}/actions/{aid}` | 更新行动状态 |
| GET | `/api/goals/priorities/sorted` | 优先级排序 |
| GET | `/api/goals/stagnant` | 停滞检测 |

### 记忆 & 知识库
| 方法 | 路径 | 说明 |
|------|------|------|
| POST | `/api/memory/memories` | 创建记忆 |
| GET | `/api/memory/memories` | 列出记忆 |
| GET | `/api/memory/memories/search` | 语义搜索记忆 |
| POST | `/api/knowledge/documents` | 导入文档 |
| POST | `/api/knowledge/documents/upload` | 上传文件 |
| GET | `/api/knowledge/search` | 语义搜索知识库 |
| POST | `/api/knowledge/ask` | RAG 问答 |

### 复盘 & 通知
| 方法 | 路径 | 说明 |
|------|------|------|
| POST | `/api/reviews/trigger/daily` | 触发每日复盘 |
| POST | `/api/reviews/trigger/weekly` | 触发每周复盘 |
| POST | `/api/reviews/trigger/monthly` | 触发每月复盘 |
| POST | `/api/reviews/trigger/morning-brief` | 触发晨间简报 |
| GET | `/api/notifications/` | 列出通知 |
| PUT | `/api/notifications/{id}/read` | 标记已读 |
| PUT | `/api/notifications/read-all` | 全部已读 |

### 系统
| 方法 | 路径 | 说明 |
|------|------|------|
| GET | `/api/system/health` | 健康检查 |
| GET | `/api/system/llm-providers` | LLM 提供者列表 |
| GET | `/api/system/info` | 系统统计 |

## 配置说明

| 环境变量 | 默认值 | 说明 |
|----------|--------|------|
| `LLM_API_KEY` | 必填 | DeepSeek API Key |
| `LLM_BASE_URL` | `https://api.deepseek.com/v1` | LLM API 地址 |
| `LLM_MODEL` | `deepseek-chat` | 默认模型 |
| `OPENAI_API_KEY` | （可选） | OpenAI API Key |
| `ANTHROPIC_API_KEY` | （可选） | Claude API Key |
| `OLLAMA_BASE_URL` | （可选） | Ollama 本地地址 |
| `DATA_DIR` | `./backend/data` | 数据目录 |
| `PORT` | `8000` | 后端端口 |

## 数据库

全部数据存储于本地 SQLite 文件（`backend/data/personal_ai.db`），启用 WAL 模式和外键约束。

包含 11 张表：`conversations`、`messages`、`goals`、`actions`、`events`、`memories`、`reviews`、`notifications`、`schedules`、`activity_log`、`documents`。

向量数据存储于 ChromaDB（`backend/data/vectors/`），包含 `memories` 和 `knowledge` 两个 collection。

## 定时任务

| 任务 | 时间 | 说明 |
|------|------|------|
| 晨间简报 | 每天 8:00 | Top 3 优先目标 + 停滞提醒 |
| Deadline 预警 | 每天 9:00 | 抽查 1/3 天内截止的目标 |
| 每日复盘 | 每天 21:00 | 今日事件摘要 + 目标进展 |
| 每周复盘 | 每周日 20:00 | 本周进展 + 下周重点 |
| 每月复盘 | 每月 1 日 20:00 | 目标完成率 + 兴趣发现 |

## 桌面快捷键

| 快捷键 | 功能 |
|--------|------|
| Alt + Space | 唤出快捷对话窗口 |
| Alt + Shift + I | 快速捕获（Inbox） |

## 许可证

MIT
