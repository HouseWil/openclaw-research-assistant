"""
RAG (Retrieval Augmented Generation) module for OpenClaw Research Assistant.

Handles document text extraction, chunking, embedding via OpenAI API, and
cosine-similarity search.  Falls back to keyword scoring when embeddings are
unavailable (Anthropic provider or API error).
"""

from __future__ import annotations

import json
import logging
import re
import shutil
import time
from pathlib import Path
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)

# ── Constants ────────────────────────────────────────────────────────────────

CHUNK_SIZE: int = 1000           # characters per chunk
CHUNK_OVERLAP: int = 200         # overlap between adjacent chunks
EMBEDDING_MODEL: str = "text-embedding-3-small"
MAX_FILE_SIZE: int = 50 * 1024 * 1024   # 50 MB
ALLOWED_EXTENSIONS: frozenset = frozenset({".pdf", ".docx", ".txt", ".md"})


# ── Low-level helpers ─────────────────────────────────────────────────────────

def _cosine_sim(a: List[float], b: List[float]) -> float:
    """Cosine similarity between two vectors (pure Python, no numpy)."""
    dot = sum(x * y for x, y in zip(a, b))
    mag_a = sum(x * x for x in a) ** 0.5
    mag_b = sum(x * x for x in b) ** 0.5
    if not mag_a or not mag_b:
        return 0.0
    return dot / (mag_a * mag_b)


def _keyword_score(query: str, text: str) -> float:
    """Simple keyword-overlap score used when embeddings are unavailable."""
    query_tokens = set(re.findall(r"\w+", query.lower()))
    text_tokens = set(re.findall(r"\w+", text.lower()))
    if not query_tokens:
        return 0.0
    return len(query_tokens & text_tokens) / len(query_tokens)


def _chunk_text(text: str) -> List[str]:
    """Split *text* into overlapping chunks, preferring sentence/paragraph breaks."""
    text = text.strip()
    if not text:
        return []
    chunks: List[str] = []
    start = 0
    while start < len(text):
        end = min(start + CHUNK_SIZE, len(text))
        if end < len(text):
            # Try to break at a natural boundary
            for sep in ("\n\n", "\n", "。", ". ", " "):
                idx = text.rfind(sep, start + CHUNK_SIZE // 2, end)
                if idx != -1:
                    end = idx + len(sep)
                    break
        chunk = text[start:end].strip()
        if chunk:
            chunks.append(chunk)
        start = end - CHUNK_OVERLAP if end < len(text) else len(text)
    return chunks


# ── Text extraction ───────────────────────────────────────────────────────────

def _extract_pdf(path: Path) -> str:
    try:
        from pypdf import PdfReader  # type: ignore
    except ImportError as exc:
        raise RuntimeError("pypdf 未安装，请运行: pip install pypdf") from exc
    try:
        reader = PdfReader(str(path))
        return "\n\n".join(page.extract_text() or "" for page in reader.pages)
    except Exception as exc:
        raise RuntimeError(f"PDF 解析失败: {exc}") from exc


def _extract_docx(path: Path) -> str:
    try:
        from docx import Document  # type: ignore
    except ImportError as exc:
        raise RuntimeError("python-docx 未安装，请运行: pip install python-docx") from exc
    try:
        doc = Document(str(path))
        return "\n\n".join(p.text for p in doc.paragraphs if p.text.strip())
    except Exception as exc:
        raise RuntimeError(f"DOCX 解析失败: {exc}") from exc


def extract_text(path: Path) -> str:
    """Dispatch text extraction based on file extension."""
    ext = path.suffix.lower()
    if ext == ".pdf":
        return _extract_pdf(path)
    if ext == ".docx":
        return _extract_docx(path)
    # .txt / .md and any other text file
    return path.read_text(encoding="utf-8", errors="ignore")


# ── RAGManager ────────────────────────────────────────────────────────────────

class RAGManager:
    """Manage document ingestion, storage, and retrieval for RAG."""

    def __init__(self, docs_dir: Path, llm_cfg: Dict[str, Any]) -> None:
        self.docs_dir = Path(docs_dir)
        self.llm_cfg = llm_cfg
        self.index_path = self.docs_dir / "index.json"
        self.docs_dir.mkdir(parents=True, exist_ok=True)

    # ── Index helpers ─────────────────────────────────────────────────────

    def _load_index(self) -> List[Dict[str, Any]]:
        if not self.index_path.exists():
            return []
        try:
            data = json.loads(self.index_path.read_text(encoding="utf-8"))
            return data if isinstance(data, list) else []
        except Exception:
            return []

    def _save_index(self, index: List[Dict[str, Any]]) -> None:
        self.index_path.write_text(
            json.dumps(index, ensure_ascii=False, indent=2), encoding="utf-8"
        )

    def list_documents(self) -> List[Dict[str, Any]]:
        """Return all indexed document metadata."""
        return self._load_index()

    # ── Embedding ─────────────────────────────────────────────────────────

    async def _embed_texts(self, texts: List[str]) -> Optional[List[List[float]]]:
        """Fetch embeddings from OpenAI-compatible API; return None on failure."""
        provider = self.llm_cfg.get("provider", "openai")
        api_key = self.llm_cfg.get("api_key", "")
        api_base = self.llm_cfg.get("api_base", "")

        if provider == "anthropic" or not api_key:
            return None  # Anthropic has no embeddings endpoint

        try:
            from openai import AsyncOpenAI  # type: ignore

            kwargs: Dict[str, Any] = {"api_key": api_key}
            if api_base:
                kwargs["base_url"] = api_base
            client = AsyncOpenAI(**kwargs)
            response = await client.embeddings.create(input=texts, model=EMBEDDING_MODEL)
            return [item.embedding for item in response.data]
        except Exception as exc:
            logger.warning("rag_embed_failed err=%s", type(exc).__name__)
            return None

    # ── Ingestion ─────────────────────────────────────────────────────────

    async def add_document(
        self, doc_id: str, file_path: Path, filename: str
    ) -> Dict[str, Any]:
        """
        Extract, chunk, embed, and persist a document.
        Returns the document metadata dict that is stored in the index.
        """
        doc_dir = self.docs_dir / doc_id
        doc_dir.mkdir(parents=True, exist_ok=True)

        text = extract_text(file_path)
        chunks = _chunk_text(text)
        logger.info("rag_chunked doc=%s chunks=%d", doc_id, len(chunks))

        # Embed in batches of 64 to stay within API limits
        all_embeddings: Optional[List[List[float]]] = None
        if chunks:
            batch_size = 64
            batches = [chunks[i : i + batch_size] for i in range(0, len(chunks), batch_size)]
            collected: List[List[float]] = []
            failed = False
            for batch in batches:
                result = await self._embed_texts(batch)
                if result is None:
                    failed = True
                    break
                collected.extend(result)
            if not failed and len(collected) == len(chunks):
                all_embeddings = collected

        has_embeddings = all_embeddings is not None

        chunk_records: List[Dict[str, Any]] = []
        for i, chunk in enumerate(chunks):
            rec: Dict[str, Any] = {"index": i, "text": chunk}
            if has_embeddings:
                rec["embedding"] = all_embeddings[i]  # type: ignore[index]
            chunk_records.append(rec)

        chunks_path = doc_dir / "chunks.json"
        chunks_path.write_text(
            json.dumps({"chunks": chunk_records}, ensure_ascii=False),
            encoding="utf-8",
        )

        doc_meta: Dict[str, Any] = {
            "id": doc_id,
            "filename": filename,
            "ext": file_path.suffix.lower(),
            "chunk_count": len(chunks),
            "has_embeddings": has_embeddings,
            "char_count": len(text),
            "created_at": int(time.time()),
        }

        index = self._load_index()
        index = [d for d in index if d["id"] != doc_id]
        index.append(doc_meta)
        self._save_index(index)

        return doc_meta

    # ── Search ────────────────────────────────────────────────────────────

    async def search(self, query: str, top_k: int = 5) -> List[Dict[str, Any]]:
        """
        Return the top_k most relevant chunks across all indexed documents.
        Each result dict contains: doc_id, filename, text, score.
        """
        query = query.strip()
        if not query:
            return []

        index = self._load_index()
        if not index:
            return []

        # Compute query embedding once
        query_embedding: Optional[List[float]] = None
        emb_result = await self._embed_texts([query])
        if emb_result:
            query_embedding = emb_result[0]

        results: List[Dict[str, Any]] = []
        for doc_meta in index:
            doc_id = doc_meta["id"]
            chunks_path = self.docs_dir / doc_id / "chunks.json"
            if not chunks_path.exists():
                continue
            try:
                data = json.loads(chunks_path.read_text(encoding="utf-8"))
                chunk_records = data.get("chunks", [])
            except Exception:
                continue

            for chunk in chunk_records:
                text = chunk.get("text", "")
                if not text:
                    continue
                if query_embedding and chunk.get("embedding"):
                    score = _cosine_sim(query_embedding, chunk["embedding"])
                else:
                    score = _keyword_score(query, text)
                results.append(
                    {
                        "doc_id": doc_id,
                        "filename": doc_meta.get("filename", doc_id),
                        "text": text,
                        "score": score,
                    }
                )

        results.sort(key=lambda x: x["score"], reverse=True)
        return results[:top_k]

    # ── Deletion ──────────────────────────────────────────────────────────

    def delete_document(self, doc_id: str) -> bool:
        """Remove a document from the index and delete its on-disk data."""
        index = self._load_index()
        new_index = [d for d in index if d["id"] != doc_id]
        if len(new_index) == len(index):
            return False
        self._save_index(new_index)
        doc_dir = self.docs_dir / doc_id
        if doc_dir.exists():
            shutil.rmtree(doc_dir)
        return True
