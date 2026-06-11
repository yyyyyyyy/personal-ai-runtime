"""Egress gate — LLM outbound audit (EGRESS_RFC v0.1)."""

from app.core.runtime.egress.egress_gate import prepare_llm_egress

__all__ = ["prepare_llm_egress"]
