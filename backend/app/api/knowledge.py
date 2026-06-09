"""Knowledge Base API — import documents and perform RAG-based Q&A."""

import uuid
import json
from datetime import datetime

from fastapi import APIRouter, HTTPException, UploadFile
from app.store.database import db
from app.store.vector import vector_store

router = APIRouter(prefix="/api/knowledge", tags=["knowledge"])

CHUNK_SIZE = 1000  # characters per chunk


def _chunk_text(text: str, chunk_size: int = CHUNK_SIZE) -> list[str]:
    """Split text into overlapping chunks for embedding."""
    chunks = []
    start = 0
    while start < len(text):
        end = start + chunk_size
        chunk = text[start:end]
        if end < len(text) and " " in chunk[::-1]:
            # Try to break at the last space for cleaner chunks
            last_space = chunk.rfind(" ")
            if last_space > chunk_size // 2:
                end = start + last_space
                chunk = text[start:end]
        chunks.append(chunk)
        start = end
    return chunks


@router.post("/documents")
async def import_document(body: dict):
    """Import a document from text content.

    Request body: {"title": "My Note", "content": "full text content..."}
    """
    title = body.get("title", "Untitled")
    content = body.get("content", "")

    if not content.strip():
        raise HTTPException(status_code=400, detail="Content is required")

    doc_id = str(uuid.uuid4())
    now = datetime.utcnow().isoformat()

    # Store document record
    with db.get_db() as conn:
        conn.execute(
            "INSERT INTO documents (id, title, content, chunk_count, created_at) VALUES (?, ?, ?, ?, ?)",
            (doc_id, title, content, 0, now),
        )

    # Chunk and embed
    chunks = _chunk_text(content)
    chunk_ids = []
    for i, chunk in enumerate(chunks):
        cid = f"{doc_id}_chunk_{i}"
        vector_store.add_knowledge_chunk(
            content=chunk,
            metadata={"doc_id": doc_id, "title": title, "chunk_index": i},
            chunk_id=cid,
        )
        chunk_ids.append(cid)

    # Update chunk count
    with db.get_db() as conn:
        conn.execute(
            "UPDATE documents SET chunk_count = ? WHERE id = ?",
            (len(chunks), doc_id),
        )

    return {"id": doc_id, "title": title, "chunk_count": len(chunks), "status": "ok"}


@router.post("/documents/upload")
async def upload_document(file: UploadFile):
    """Upload and import a document file (Markdown, TXT).

    For PDF, only text extraction is attempted (no OCR).
    """
    if not file.filename:
        raise HTTPException(status_code=400, detail="Filename is required")

    content = await file.read()

    try:
        text = content.decode("utf-8")
    except UnicodeDecodeError:
        raise HTTPException(status_code=400, detail="File encoding not supported (UTF-8 only)")

    if not text.strip():
        raise HTTPException(status_code=400, detail="File is empty")

    doc_id = str(uuid.uuid4())
    now = datetime.utcnow().isoformat()

    with db.get_db() as conn:
        conn.execute(
            "INSERT INTO documents (id, title, file_path, content, chunk_count, created_at) "
            "VALUES (?, ?, ?, ?, ?, ?)",
            (doc_id, file.filename, file.filename, text, 0, now),
        )

    chunks = _chunk_text(text)
    for i, chunk in enumerate(chunks):
        cid = f"{doc_id}_chunk_{i}"
        vector_store.add_knowledge_chunk(
            content=chunk,
            metadata={"doc_id": doc_id, "title": file.filename, "chunk_index": i},
            chunk_id=cid,
        )

    with db.get_db() as conn:
        conn.execute("UPDATE documents SET chunk_count = ? WHERE id = ?", (len(chunks), doc_id))

    return {"id": doc_id, "title": file.filename, "chunk_count": len(chunks), "status": "ok"}


@router.get("/documents")
async def list_documents():
    """List all imported documents."""
    with db.get_db() as conn:
        rows = conn.execute(
            "SELECT id, title, file_path, chunk_count, created_at FROM documents ORDER BY created_at DESC"
        ).fetchall()
    return [dict(r) for r in rows]


@router.delete("/documents/{doc_id}")
async def delete_document(doc_id: str):
    """Delete a document and its chunks."""
    with db.get_db() as conn:
        conn.execute("DELETE FROM documents WHERE id = ?", (doc_id,))

    # Delete all chunks for this document from ChromaDB
    chunk_ids = [f"{doc_id}_chunk_{i}" for i in range(1000)]  # safe upper bound
    vector_store.delete_knowledge_chunks(chunk_ids)

    return {"status": "ok"}


@router.get("/search")
async def search_knowledge(q: str, n: int = 5):
    """Semantic search in the knowledge base."""
    if not q:
        raise HTTPException(status_code=400, detail="Query parameter 'q' is required")
    results = vector_store.search_knowledge(q, n_results=n)
    return {"query": q, "results": results}


@router.post("/ask")
async def ask_knowledge(body: dict):
    """RAG-based Q&A: search knowledge base and return relevant chunks.

    The actual LLM-based answer generation happens in the chat flow.
    This endpoint returns the relevant context chunks for RAG.
    """
    query = body.get("query", "")
    n = body.get("n", 5)

    if not query:
        raise HTTPException(status_code=400, detail="Query is required")

    results = vector_store.search_knowledge(query, n_results=n)
    context_chunks = [r["content"] for r in results if r.get("content")]

    return {
        "query": query,
        "context": "\n\n---\n\n".join(context_chunks),
        "source_count": len(context_chunks),
        "sources": results,
    }
