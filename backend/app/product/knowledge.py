"""Knowledge base product service — document registry + vector chunks.

Owns app_settings(category='knowledge_docs') and Chroma knowledge collection.
API routes must call this module instead of importing ``app.store`` directly.
"""

from __future__ import annotations

import json
import logging
import re
import uuid
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from app.core.runtime.kernel_instance import kernel
from app.store.database import db
from app.store.text_chunker import ChunkConfig, chunk_text
from app.store.vector import vector_store

logger = logging.getLogger(__name__)

KNOWLEDGE_CATEGORY = "knowledge_docs"
MAX_FILE_SIZE = 10 * 1024 * 1024
ALLOWED_EXTENSIONS = {".pdf", ".md", ".txt", ".markdown", ".json", ".csv", ".docx"}

_MAX_FILENAME_LENGTH = 200
_FILENAME_CONTROL_RE = re.compile(r"[\x00-\x1f\x7f]")


class KnowledgeError(Exception):
    """Domain error with an HTTP-friendly status code."""

    def __init__(self, detail: str, *, status_code: int = 400):
        super().__init__(detail)
        self.detail = detail
        self.status_code = status_code


def sanitize_filename(filename: str) -> str:
    """Sanitize user-supplied filename for safe storage in metadata."""
    name = Path(filename).name
    name = _FILENAME_CONTROL_RE.sub("", name)
    if len(name) > _MAX_FILENAME_LENGTH:
        name = name[:_MAX_FILENAME_LENGTH]
    return name or "unnamed"


def load_documents() -> dict[str, dict]:
    """Load document registry from app_settings table."""
    try:
        with db.get_db() as conn:
            row = conn.execute(
                "SELECT data_json FROM app_settings WHERE category = ?",
                (KNOWLEDGE_CATEGORY,),
            ).fetchone()
        if row:
            return json.loads(row["data_json"])
    except Exception:
        logger.warning("Failed to load knowledge documents", exc_info=True)
    return {}


def save_documents(docs: dict[str, dict]) -> None:
    """Persist document registry and emit an audit event (metadata only)."""
    now = datetime.now(UTC).isoformat()
    with db.get_db() as conn:
        conn.execute(
            """INSERT INTO app_settings (category, data_json, updated_at)
               VALUES (?, ?, ?)
               ON CONFLICT(category) DO UPDATE SET
                 data_json = excluded.data_json,
                 updated_at = excluded.updated_at""",
            (KNOWLEDGE_CATEGORY, json.dumps(docs, ensure_ascii=False), now),
        )
    kernel.emit_event(
        "AppConfigChanged",
        "app_config",
        KNOWLEDGE_CATEGORY,
        payload={
            "category": KNOWLEDGE_CATEGORY,
            "doc_count": len(docs),
            "updated_at": now,
        },
        actor="user",
    )


def extract_text(file_path: Path, filename: str) -> str:
    ext = Path(filename).suffix.lower()
    if ext in (".txt", ".md", ".markdown", ".csv"):
        return file_path.read_text(encoding="utf-8")
    if ext == ".json":
        data = json.loads(file_path.read_text(encoding="utf-8"))
        return json.dumps(data, ensure_ascii=False, indent=2)
    if ext == ".pdf":
        try:
            from pypdf import PdfReader
        except ImportError as e:
            raise KnowledgeError(
                "PDF support requires pypdf. Install with: pip install pypdf",
                status_code=500,
            ) from e
        reader = PdfReader(str(file_path))
        text = ""
        for page in reader.pages:
            text += page.extract_text() or ""
        return text
    if ext == ".docx":
        try:
            from docx import Document
        except ImportError as e:
            raise KnowledgeError(
                "DOCX support requires python-docx. Install with: pip install python-docx",
                status_code=500,
            ) from e
        doc = Document(str(file_path))
        return "\n".join(p.text for p in doc.paragraphs if p.text.strip())
    raise KnowledgeError(f"不支持的文件格式: {ext}")


def ingest_upload(*, filename: str, content: bytes) -> dict[str, Any]:
    """Chunk, embed, and register an uploaded document. Returns the registry entry."""
    if not filename:
        raise KnowledgeError("文件名不能为空")

    ext = Path(filename).suffix.lower()
    if ext not in ALLOWED_EXTENSIONS:
        raise KnowledgeError(
            f"不支持的文件格式: {ext}。支持: {', '.join(sorted(ALLOWED_EXTENSIONS))}"
        )

    if len(content) > MAX_FILE_SIZE:
        raise KnowledgeError(f"文件过大，最大 {MAX_FILE_SIZE // 1024 // 1024} MB")

    import tempfile

    with tempfile.NamedTemporaryFile(suffix=ext, delete=False) as tmp:
        tmp.write(content)
        tmp_path = Path(tmp.name)

    try:
        text = extract_text(tmp_path, filename)
    finally:
        tmp_path.unlink()

    if not text.strip():
        raise KnowledgeError("文件内容为空")

    chunks = chunk_text(text, ChunkConfig())
    doc_id = str(uuid.uuid4())
    chunk_ids: list[str] = []
    safe_name = sanitize_filename(filename)

    for i, chunk in enumerate(chunks):
        chunk_id = f"{doc_id}_chunk_{i}"
        vector_store.add_knowledge_chunk(
            content=chunk,
            metadata={
                "source_file": safe_name,
                "chunk_index": i,
                "total_chunks": len(chunks),
                "document_id": doc_id,
            },
            chunk_id=chunk_id,
        )
        chunk_ids.append(chunk_id)

    docs = load_documents()
    docs[doc_id] = {
        "id": doc_id,
        "filename": filename,
        "size": len(content),
        "chunks": len(chunks),
        "chunk_ids": chunk_ids,
        "uploaded_at": datetime.now(UTC).isoformat(),
    }
    save_documents(docs)
    return docs[doc_id]


def list_documents() -> list[dict[str, Any]]:
    docs = load_documents()
    return sorted(docs.values(), key=lambda d: d.get("uploaded_at", ""), reverse=True)


def delete_document(document_id: str) -> None:
    docs = load_documents()
    if document_id not in docs:
        raise KnowledgeError("文档不存在", status_code=404)

    doc = docs[document_id]
    vector_store.delete_knowledge_chunks(doc["chunk_ids"])
    del docs[document_id]
    save_documents(docs)


def search_documents(query: str, *, n_results: int = 5) -> list[dict[str, Any]]:
    """Semantic search over knowledge chunks (sync; call via to_thread from async)."""
    return vector_store.search_knowledge(query, n_results)
