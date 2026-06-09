"""Daily memory confidence decay for derived beliefs."""

from app.core.runtime.kernel_instance import kernel
from app.store.database import db


def run_memory_decay(threshold: float = 0.3, decay_to: float = 0.1) -> int:
    """Emit MemoryDecayed for stale low-confidence memories."""
    count = 0
    with db.get_db() as conn:
        rows = conn.execute(
            """SELECT id, confidence FROM memories
               WHERE confidence > ? AND confidence < 0.8
               AND (decayed_at IS NULL OR decayed_at < datetime('now', '-7 days'))
               LIMIT 50""",
            (decay_to,),
        ).fetchall()

    for row in rows:
        mem = dict(row)
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
