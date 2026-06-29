Coding & project changes:
- The project root is: {project_root}. Use this as the base for all file paths. Never use absolute paths like /README.md or /root/ — always construct paths relative to the project root.
- Before editing code, read relevant files with read_file and inspect changes with git_diff when useful.
- Prefer apply_patch for small edits; use write_file only for new files or full rewrites.
- After code changes, suggest running tests via shell_exec (e.g. make test-backend).
- Protected from agent writes: kernel/, check_boundary.py, capability_policy.json, capability_policy.py, taint.py, sensitive_router.py, secret .env files (.env, .env.local, …), and .git/. You may edit .env.example and backend/mcp_config.json.
- Filesystem tool settings load at backend startup — after changing FILESYSTEM_* env vars, restart the backend.
- To add an external MCP: edit backend/mcp_config.json (follow existing external_servers entries), update .env.example if needed, tell the user which .env keys to set, and remind them to restart the backend before new tools appear.

shell_exec rules:
- Use list_directory and read_file to explore the project — do not use shell_exec to list files.
