"""Knowledge Base API — document upload, list, search, and delete.

Documents are persisted in the app_settings table (category='knowledge_docs')
alongside ChromaDB embeddings, surviving backend restarts.
"""

import json
import logging
import re
import uuid
from datetime import UTC, datetime
from pathlib import Path

from fastapi import APIRouter, File, HTTPException, Query, UploadFile

from app.store.database import db
from app.store.text_chunker import ChunkConfig, chunk_text
from app.store.vector import vector_store

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/knowledge", tags=["knowledge"])

KNOWLEDGE_CATEGORY = "knowledge_docs"
MAX_FILE_SIZE = 10 * 1024 * 1024
ALLOWED_EXTENSIONS = {".pdf", ".md", ".txt", ".markdown", ".json", ".csv", ".docx"}

_MAX_FILENAME_LENGTH = 200
_FILENAME_CONTROL_RE = re.compile(r"[\x00-\x1f\x7f]")


def _sanitize_filename(filename: str) -> str:
    """Sanitize user-supplied filename for safe storage in metadata."""
    name = Path(filename).name
    name = _FILENAME_CONTROL_RE.sub("", name)
    if len(name) > _MAX_FILENAME_LENGTH:
        name = name[:_MAX_FILENAME_LENGTH]
    return name or "unnamed"


def _load_documents() -> dict[str, dict]:
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


def _save_documents(docs: dict[str, dict]) -> None:
    """Persist document registry to app_settings table."""
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
    # v0.3.0: emit audit event so knowledge-doc updates are visible in the
    # event stream. Metadata only — document content stays in app_settings.
    from app.core.runtime.kernel_instance import kernel
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


def _extract_text(file_path: Path, filename: str) -> str:
    ext = Path(filename).suffix.lower()
    if ext in (".txt", ".md", ".markdown", ".csv"):
        return file_path.read_text(encoding="utf-8")
    elif ext == ".json":
        data = json.loads(file_path.read_text(encoding="utf-8"))
        return json.dumps(data, ensure_ascii=False, indent=2)
    elif ext == ".pdf":
        try:
            from pypdf import PdfReader
        except ImportError as e:
            raise HTTPException(
                status_code=500,
                detail="PDF support requires pypdf. Install with: pip install pypdf",
            ) from e
        reader = PdfReader(str(file_path))
        text = ""
        for page in reader.pages:
            text += page.extract_text() or ""
        return text
    elif ext == ".docx":
        try:
            from docx import Document
        except ImportError as e:
            raise HTTPException(
                status_code=500,
                detail="DOCX support requires python-docx. Install with: pip install python-docx",
            ) from e
        doc = Document(str(file_path))
        return "\n".join(p.text for p in doc.paragraphs if p.text.strip())
    else:
        raise HTTPException(status_code=400, detail=f"不支持的文件格式: {ext}")


@router.post("/upload")
async def upload_document(file: UploadFile = File(...)):
    if not file.filename:
        raise HTTPException(status_code=400, detail="文件名不能为空")

    ext = Path(file.filename).suffix.lower()
    if ext not in ALLOWED_EXTENSIONS:
        raise HTTPException(
            status_code=400,
            detail=f"不支持的文件格式: {ext}。支持: {', '.join(sorted(ALLOWED_EXTENSIONS))}",
        )

    content = await file.read()
    if len(content) > MAX_FILE_SIZE:
        raise HTTPException(status_code=400, detail=f"文件过大，最大 {MAX_FILE_SIZE // 1024 // 1024} MB")

    import tempfile
    with tempfile.NamedTemporaryFile(suffix=ext, delete=False) as tmp:
        tmp.write(content)
        tmp_path = Path(tmp.name)

    try:
        text = _extract_text(tmp_path, file.filename)
    finally:
        tmp_path.unlink()

    if not text.strip():
        raise HTTPException(status_code=400, detail="文件内容为空")

    chunks = chunk_text(text, ChunkConfig())
    doc_id = str(uuid.uuid4())
    chunk_ids = []

    for i, chunk in enumerate(chunks):
        chunk_id = f"{doc_id}_chunk_{i}"
        safe_name = _sanitize_filename(file.filename)
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

    docs = _load_documents()
    docs[doc_id] = {
        "id": doc_id,
        "filename": file.filename,
        "size": len(content),
        "chunks": len(chunks),
        "chunk_ids": chunk_ids,
        "uploaded_at": datetime.now(UTC).isoformat(),
    }
    _save_documents(docs)

    return {"ok": True, "document": docs[doc_id]}


@router.get("/documents")
async def list_documents():
    docs = _load_documents()
    items = sorted(docs.values(), key=lambda d: d.get("uploaded_at", ""), reverse=True)
    return {"documents": items, "total": len(items)}


@router.delete("/documents/{document_id}")
async def delete_document(document_id: str):
    docs = _load_documents()
    if document_id not in docs:
        raise HTTPException(status_code=404, detail="文档不存在")

    doc = docs[document_id]
    vector_store.delete_knowledge_chunks(doc["chunk_ids"])
    del docs[document_id]
    _save_documents(docs)

    return {"ok": True}


@router.post("/search")
async def search_knowledge(
    query: str = Query(..., description="搜索查询"),
    n_results: int = Query(5, ge=1, le=20),
):
    """Search knowledge documents semantically. **@public** SDK surface — external agents may call this to recall from the user's document library."""
    results = vector_store.search_knowledge(query, n_results=n_results)
    return {"results": results, "query": query, "total": len(results)}
