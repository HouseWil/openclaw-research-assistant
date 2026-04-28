"""
Docs router - document upload, listing, deletion and search for RAG.
"""

from __future__ import annotations

import re
import shutil
import sys
import uuid
from pathlib import Path

import aiofiles
from fastapi import APIRouter, File, HTTPException, UploadFile

sys.path.insert(0, str(Path(__file__).parent.parent))
from config_manager import ConfigManager
from rag import ALLOWED_EXTENSIONS, MAX_FILE_SIZE, RAGManager

BASE_DIR = Path(__file__).parent.parent.parent
CONFIG_DIR = BASE_DIR / "config"
DOCS_DIR = BASE_DIR / "docs"

# UUID v4 pattern used to validate doc_id path parameters
_UUID_RE = re.compile(
    r"^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$"
)

router = APIRouter()


def _get_llm_cfg() -> dict:
    mgr = ConfigManager(CONFIG_DIR)
    cfg = mgr.get_openclaw_config()
    return cfg.get("llm", {})


def _validate_doc_id(doc_id: str) -> str:
    """Return normalised doc_id or raise 400 on invalid format."""
    normalised = doc_id.strip().lower()
    if not _UUID_RE.match(normalised):
        raise HTTPException(status_code=400, detail="无效的文档 ID")
    return normalised


@router.get("/")
async def list_docs():
    """Return metadata for all indexed documents."""
    mgr = RAGManager(DOCS_DIR, _get_llm_cfg())
    return {"documents": mgr.list_documents()}


@router.post("/upload")
async def upload_doc(file: UploadFile = File(...)):
    """
    Upload a PDF / DOCX / TXT / MD file.
    The file is saved to docs/{uuid}/ and chunked + embedded for RAG.
    """
    filename = file.filename or "untitled"
    ext = Path(filename).suffix.lower()

    if ext not in ALLOWED_EXTENSIONS:
        raise HTTPException(
            status_code=400,
            detail=(
                f"不支持的文件格式 '{ext}'。"
                f"支持格式：{', '.join(sorted(ALLOWED_EXTENSIONS))}"
            ),
        )

    content = await file.read()
    if len(content) > MAX_FILE_SIZE:
        raise HTTPException(
            status_code=413,
            detail=f"文件过大（最大 {MAX_FILE_SIZE // 1024 // 1024} MB）",
        )

    doc_id = str(uuid.uuid4())
    doc_dir = DOCS_DIR / doc_id
    doc_dir.mkdir(parents=True, exist_ok=True)
    original_path = doc_dir / f"original{ext}"

    async with aiofiles.open(original_path, "wb") as fh:
        await fh.write(content)

    mgr = RAGManager(DOCS_DIR, _get_llm_cfg())
    try:
        doc_meta = await mgr.add_document(doc_id, original_path, filename)
    except Exception as exc:
        shutil.rmtree(doc_dir, ignore_errors=True)
        raise HTTPException(status_code=500, detail=f"文档处理失败：{exc}") from exc

    return {"status": "ok", "document": doc_meta}


@router.delete("/{doc_id}")
async def delete_doc(doc_id: str):
    """Delete a document and all its indexed data."""
    doc_id = _validate_doc_id(doc_id)
    mgr = RAGManager(DOCS_DIR, _get_llm_cfg())
    if not mgr.delete_document(doc_id):
        raise HTTPException(status_code=404, detail=f"文档 '{doc_id}' 不存在")
    return {"status": "ok", "message": "文档已删除"}


@router.get("/search")
async def search_docs(query: str, top_k: int = 5):
    """Search the knowledge base and return the most relevant chunks."""
    if not query.strip():
        raise HTTPException(status_code=400, detail="查询内容不能为空")
    top_k = max(1, min(top_k, 20))
    mgr = RAGManager(DOCS_DIR, _get_llm_cfg())
    results = await mgr.search(query, top_k=top_k)
    return {"results": results}
