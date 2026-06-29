"""Pattern Runtime — statistical aggregation over ActivityNormalized events.

Pattern is a Projection Primitive (like Goal / Memory): purely statistical,
no interpretation.  The Aggregator subscribes to ActivityNormalized events,
maintains sliding-window counters, and emits PatternDetected when a pattern
crosses the significance threshold.

Per Cognitive Architecture:
    Evidence (ActivityNormalized) → Pattern (PatternDetected) → Belief
"""

from .aggregators import PatternAggregator, pattern_aggregator

__all__ = ["PatternAggregator", "pattern_aggregator"]
