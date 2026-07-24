# ADR-R011 — Chat approval continuation (C2)

| Field | Content |
|-------|---------|
| Decision | 审批后执行已批准工具 + `Brain.continue_after_tool_result`（无 tools 的 one-shot）；**不**跨进程重开完整 Brain 工具环 |
| Context | 核实：`approve_handlers` → `continue_after_tool_result`；无 Chat PlanResume；SSE 队列内存态 |
| Evidence | `approve_handlers.py`, `brain_llm_client.py` / `brain_llm_ops.py` |
| Consequences + | 语义清晰；避免半开环 cursor 复杂度 |
| Consequences − | 进程死亡后不能静默续跑多步 tool loop；用户需新回合 |
| Still valid? | Yes（C1 未选） |
