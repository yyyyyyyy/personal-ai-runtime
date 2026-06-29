# Personal AI Runtime

> **Your personal AI. Switch models without losing yourself.**

Your AI should belong to you — not OpenAI, not Apple, not Google. Yours.

No matter how many times you switch models or providers, your AI remembers you, understands you, and respects your choices.

**中文文档：** [README.md](README.md)

---

## What it does

| Chat | Goals | Inbox |
|:---:|:---:|:---:|
| ![Chat](docs/assets/chat.png) | ![Goals](docs/assets/goals.png) | ![Inbox](docs/assets/inbox.png) |

| Dashboard | Memories |
|:---:|:---:|
| ![Dashboard](docs/assets/dashboard.png) | ![Memories](docs/assets/memories.png) |

- **Chat** — Context-aware conversations with memory and goal awareness.
- **Inbox** — Email polling, classification, and summaries. Ask AI to handle your mail.
- **Goals** — Goal and action tracking with stagnation detection and proactive reminders.
- **Memories** — Long-term memory that grows over time. Browse, search, and edit.
- **Dashboard** — System overview with usage stats and cost trends.
- **Approvals** — High-risk actions (write files, send emails, run commands) require your consent.

---

## Quick start

```bash
# 1. Clone
git clone https://github.com/yyyyyyyy/personal-ai-runtime.git
cd personal-ai-runtime

# 2. Configure LLM
cp .env.example .env
# Edit .env: set LLM_API_KEY (DeepSeek recommended, includes free credits)

# 3. Install & start
make install && make dev

# 4. Open browser
# http://localhost:5173
```

Docker:

```bash
docker compose up --build
```

See [.env.example](.env.example) for all variables. More setup options in the [User Guide](docs/guides/USER_GUIDE.md).

---

## Long-term memory

- Every memory traceable to source (which conversation), visible, editable, auditable
- Switch models by changing one config line. Memories survive.
- Data stored on your machine. Full JSON export.

---

## Core idea

If your AI doesn't know you, it's just a tool.

If it knows you — but only inside one model, one vendor — you don't own that relationship.

This project exists so that **you never have to start over with a new AI.**

Switch models as often as you like. Your AI still remembers you.

Technically, this is achieved through Event Sourcing: every interaction is recorded as an immutable event stream. Memory and state are derived from events, and can be fully exported and rebuilt at any time.

---

## Requirements

- Python 3.12+
- Node.js 20+
- (Optional) Ollama — local memory extraction
- (Optional) Gmail App Password — smart inbox
- (Optional) Docker

---

## Data sovereignty

All your data lives on your machine. Conversations, memories, goals, decisions — all yours.

- **Event Log is immutable** — Database-level enforcement against UPDATE/DELETE.
- **State is rebuildable** — Clear all projection tables and rebuild deterministically from the Event Log.
- **Data is exportable** — One-click export of the complete event stream as JSON.

```bash
curl -X POST http://localhost:8000/api/system/export \
  -H "Content-Type: application/json" \
  -d '{"confirm":"EXPORT_ALL_DATA"}' \
  -o backup.json
```

---

## Learn more

| You want to know | Read this |
|-----------------|-----------|
| Why now? | [WHY_NOW](docs/product/WHY_NOW.md) (Chinese) |
| What we believe | [MANIFESTO](docs/product/MANIFESTO.md) (Chinese) |
| Positioning & Philosophy | [POSITIONING](docs/product/POSITIONING.md) (Chinese) |
| How to use | [USER_GUIDE](docs/guides/USER_GUIDE.md) (Chinese) |
| Architecture | [ARCHITECTURE](docs/architecture/ARCHITECTURE.md) |
| Contributing | [CONTRIBUTING](CONTRIBUTING.md) |
| Developer guide | [DEVELOPER_GUIDE](docs/guides/DEVELOPER_GUIDE.md) |
| API docs | [API](docs/reference/API.md) + Swagger UI (`/docs`) |
| Roadmap | [ROADMAP](docs/product/ROADMAP.md) |
| Engineering docs | [engineering/](docs/engineering/) |

---

## Security note

- **Binds to 127.0.0.1 by default, no authentication.** Designed for local single-user use.
- **Never deploy to the public internet.** High-risk tools (`shell_exec`, `write_file`, `send_email`) are built in. If exposing to a LAN or binding to `0.0.0.0`, set both `AUTH_TOKEN` and `VITE_AUTH_TOKEN` in `.env` (they must match; see [CONFIGURATION](docs/reference/CONFIGURATION.md)).
- **High-risk operations require your approval.** File writes, email sends, command execution trigger confirmation dialogs.
- **Taint tracking.** Content ingested from external sources (emails, web scrapes) triggers risk escalation to prevent prompt injection.

---

## FAQ

**"ModuleNotFoundError: No module named 'app'"** — Run uvicorn from `backend/` directory.

**Frontend can't reach backend / CORS error** — If Vite picked port 5174, add `http://localhost:5174` to `CORS_ORIGINS` in `.env`.

**Chat stuck on "thinking"** — Check if `LLM_API_KEY` is valid.

**ChromaDB slow first start** — Embedding model downloads on first run. Chroma internal WAL warnings can be ignored.
