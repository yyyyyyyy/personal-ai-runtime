"""Knowledge Base API — document upload, list, search, and delete."""

import asyncio

from fastapi import APIRouter, File, HTTPException, Query, UploadFile

from app.product import knowledge as knowledge_service
from app.product.knowledge import MAX_FILE_SIZE

router = APIRouter(tags=["knowledge"])


@router.post("/upload")
async def upload_document(file: UploadFile = File(...)):
    content = await file.read(MAX_FILE_SIZE + 1)
    if len(content) > MAX_FILE_SIZE:
        raise HTTPException(
            status_code=413,
            detail=f"File too large (max {MAX_FILE_SIZE // 1024 // 1024} MB)",
        )
    try:
        document = await asyncio.to_thread(
            knowledge_service.ingest_upload,
            filename=file.filename or "",
            content=content,
        )
    except knowledge_service.KnowledgeError as e:
        raise HTTPException(status_code=e.status_code, detail=e.detail) from e
    return {"ok": True, "document": document}


@router.get("/documents")
async def list_documents():
    items = await asyncio.to_thread(knowledge_service.list_documents)
    return {"documents": items, "total": len(items)}


@router.delete("/documents/{document_id}")
async def delete_document(document_id: str):
    try:
        await asyncio.to_thread(knowledge_service.delete_document, document_id)
    except knowledge_service.KnowledgeError as e:
        raise HTTPException(status_code=e.status_code, detail=e.detail) from e
    return {"ok": True}


@router.get("/search")
async def search_knowledge(
    query: str = Query(..., description="搜索查询"),
    n_results: int = Query(5, ge=1, le=20),
):
    """Search knowledge documents semantically. **@public** SDK surface — external agents may call this to recall from the user's document library."""
    results = await asyncio.to_thread(
        knowledge_service.search_documents, query, n_results=n_results
    )
    return {"results": results, "query": query, "total": len(results)}
