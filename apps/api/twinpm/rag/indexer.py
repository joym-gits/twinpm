"""Build document chunks and embeddings for pgvector."""

from __future__ import annotations

import uuid
from typing import Any

from sqlalchemy import delete, insert
from sqlalchemy.ext.asyncio import AsyncSession

from twinpm.db.models import DocumentChunk
from twinpm.rag.chunking import chunk_markdown
from twinpm.rag.embedding import embed

CHUNK_NS = uuid.UUID("0b8f2f4e-3f7c-4d5e-9d1a-6a3f1f0b9c21")


def chunk_rows(documents: list[dict[str, Any]]) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for doc in documents:
        for c in chunk_markdown(doc["body"]):
            rows.append(
                {
                    "id": uuid.uuid5(CHUNK_NS, f"{doc['id']}:{c.index}"),
                    "org_id": doc["org_id"],
                    "document_id": doc["id"],
                    "chunk_index": c.index,
                    "heading": c.heading[:300],
                    "content": c.content,
                    "token_count": c.token_count,
                    "created_at": doc["created_at"],
                    "updated_at": doc["created_at"],
                    "_embed_text": f"{doc['title']}. {c.heading}. {c.content}",
                }
            )
    vecs = embed([r.pop("_embed_text") for r in rows])
    for r, v in zip(rows, vecs, strict=True):
        r["embedding"] = v.tolist()
    return rows


def embed_feedback_rows(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    vecs = embed([r["text"] for r in rows])
    return [{**r, "embedding": v.tolist()} for r, v in zip(rows, vecs, strict=True)]


async def index_document(session: AsyncSession, doc: dict[str, Any]) -> int:
    """(Re)index one document. `doc` needs id, org_id, title, body, created_at."""
    await session.execute(delete(DocumentChunk).where(DocumentChunk.document_id == doc["id"]))
    rows = chunk_rows([doc])
    if rows:
        await session.execute(insert(DocumentChunk), rows)
    return len(rows)
