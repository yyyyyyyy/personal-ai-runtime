Ops notes (filesystem / MCP):
- Filesystem tool settings load at backend startup — after changing `FILESYSTEM_*` env vars, restart the backend.
- To add an external MCP: edit `backend/mcp_config.json` (follow existing `external_servers` entries), update `.env.example` if needed, tell the user which `.env` keys to set, and remind them to restart the backend before new tools appear.
