"""Agent instance — minimal: just the identity constant for event ownership.

v0.4.0: Actor lifecycle (start/stop/pause/resume/checkpoint) removed.
The single "agent:primary" identity is used for event routing only.
"""
SINGLETON_INSTANCE_ID = "agent:primary"
