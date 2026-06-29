"""Daily memory confidence decay for derived beliefs.

Scheduled by scheduler to periodically decay low-confidence memories.
Uses kernel.emit_event() correctly — respects the Kernel Boundary.

Coverage note: excluded from pyproject.toml coverage threshold because this
function is exercised indirectly via scheduler integration tests
"""

from app.core.runtime.kernel_instance import kernel


def run_memory_decay(threshold: float = 0.3, decay_to: float = 0.1) -> int:
    """Emit MemoryDecayed for stale low-confidence memories."""
    count = 0
    candidates = kernel.query_state(
        "memories",
        confidence_gt=decay_to,
        confidence_lt=0.8,
        decay_eligible=True,
        limit=50,
    )

    for mem in candidates:
        if mem["confidence"] <= threshold:
            new_conf = max(decay_to, mem["confidence"] - 0.1)
            kernel.emit_event(
                type="MemoryDecayed",
                aggregate_type="memory",
                aggregate_id=mem["id"],
                payload={"confidence": new_conf},
                actor="scheduler",
            )
            count += 1
    return count
