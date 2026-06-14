# Experimental modules (not wired)

Code here is **not imported by the running application**. It is kept for future
integration work and should not be treated as production API.

| Module | Notes |
|--------|-------|
| `self_improver.py` | Feedback loop prototype; must migrate to `kernel.emit_event()` before activation |
| `agent_gateway.py` | Inter-agent messaging protocol stub |
| `connectors/browser_capture.py` | Browser history → Experience events |
| `connectors/git_capture.py` | Git commit metadata → Experience events |

Active connector: `app.core.connectors.calendar_capture` (see `verify_connector.py`).
