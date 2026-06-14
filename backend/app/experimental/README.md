# Experimental modules (not wired)

Code here is **not imported by the running application**. It is kept for future
integration work and should not be treated as production API.

| Module | Notes |
|--------|-------|
| `self_improver.py` | Feedback loop via `FeedbackLogged` Kernel events |
| `agent_gateway.py` | Inter-agent messaging via `AgentMessageSent/Received` events |
| `connectors/browser_capture.py` | Browser history → Experience events (stub) |
| `connectors/git_capture.py` | Git commit metadata → Experience events (stub) |

Active connector: `app.core.connectors.calendar_capture` (see `verify_connector.py`).

All experimental writes must use `kernel.emit_event()` — direct DB writes are forbidden.
