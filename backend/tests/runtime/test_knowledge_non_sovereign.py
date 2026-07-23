"""Knowledge is an explicit non-sovereignty attachment (Path B)."""

from __future__ import annotations

from app.core.runtime.kernel.constants import MEMORY_INDEX_EVENT_TYPES
from app.product import knowledge as knowledge_mod
from app.store.table_registry import (
    GOVERNED_TABLES,
    NON_SOVEREIGN_ATTACHMENTS,
    is_non_sovereign_attachment,
)


def test_knowledge_registered_as_non_sovereign_attachment():
    assert is_non_sovereign_attachment("knowledge")
    meta = NON_SOVEREIGN_ATTACHMENTS["knowledge"]
    assert meta["owner_module"] == "app.product.knowledge"
    assert meta["vector_collection"] == "knowledge"
    assert "knowledge_docs" in meta["sqlite"]
    assert knowledge_mod.KNOWLEDGE_CATEGORY == "knowledge_docs"


def test_knowledge_not_governed_table():
    assert "knowledge" not in GOVERNED_TABLES
    assert "knowledge_docs" not in GOVERNED_TABLES


def test_knowledge_not_in_memory_index_event_types():
    assert not any("knowledge" in t.lower() for t in MEMORY_INDEX_EVENT_TYPES)


def test_check_non_sovereign_attachments_script_passes():
    from scripts import check_non_sovereign_attachments as mod

    assert mod.check(verbose=False) == 0
