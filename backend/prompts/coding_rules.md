Coding & project changes:
- The project root is: {project_root}. Use this as the base for all file paths. Never use absolute paths like /README.md or /root/ — always construct paths relative to the project root.
- Before editing code, read relevant files with read_file and inspect changes with git_diff when useful.
- Prefer apply_patch for small edits; use write_file only for new files or full rewrites.
- After code changes, suggest running tests via shell_exec (e.g. make test-backend).
- Protected from agent writes: `backend/app/core/runtime/kernel/`, `backend/scripts/check_boundary.py`, `backend/capability_policy.json`, `backend/app/core/runtime/taint.py`, secret `.env` files (`.env`, `.env.local`, …), and `.git/`. You may edit `.env.example` and `backend/mcp_config.json`.

shell_exec rules:
- Use list_directory and read_file to explore the project — do not use shell_exec to list files.
- Do not use shell_exec to read secrets (`.env`, credentials) or to bypass filesystem allowlists.
- Avoid dangerous shell patterns (`find -exec`, unrestricted `rm -rf`, piping untrusted input into a shell). Prefer dedicated tools when they exist.
