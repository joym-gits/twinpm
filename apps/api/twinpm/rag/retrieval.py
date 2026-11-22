"""Hybrid retrieval: pgvector + Postgres full-text + graph-neighbourhood boost, fused by RRF."""

from __future__ import annotations

import re
import uuid
from dataclasses import dataclass
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from twinpm.db import models as m
from twinpm.rag.embedding import embed

RRF_K = 60


@dataclass
class Hit:
    chunk_id: uuid.UUID
    document_id: uuid.UUID
    title: str
    doc_type: str
    heading: str
    content: str
    score: float
    sources: list[str]


def _rrf(ranked: dict[str, list[uuid.UUID]]) -> dict[uuid.UUID, tuple[float, list[str]]]:
    out: dict[uuid.UUID, tuple[float, list[str]]] = {}
    for name, ids in ranked.items():
        for rank, cid in enumerate(ids):
            score, srcs = out.get(cid, (0.0, []))
            out[cid] = (score + 1.0 / (RRF_K + rank + 1), [*srcs, name])
    return out


async def _entity_docs(session: AsyncSession, org_id: uuid.UUID, query: str) -> set[uuid.UUID]:
    """Documents linked to entities the query mentions (epics, people, decisions)."""
    q = query.lower()
    docs: set[uuid.UUID] = set()
    epics = (await session.execute(select(m.Epic.title).where(m.Epic.org_id == org_id))).scalars()
    names = [e for e in epics if e.lower() in q]
    people = (
        await session.execute(select(m.Person.name).where(m.Person.org_id == org_id))
    ).scalars()
    names += [p for p in people if p.split()[0].lower() in re.findall(r"[a-z]+", q)]
    for name in names:
        ids = (
            await session.execute(
                select(m.Document.id)
                .where(
                    m.Document.org_id == org_id,
                    m.Document.deleted_at.is_(None),
                    (m.Document.title.ilike(f"%{name}%")) | (m.Document.body.ilike(f"%{name}%")),
                )
                .limit(8)
            )
        ).scalars()
        docs |= set(ids)
    decisions = (
        await session.execute(
            select(m.Decision.source_document_id).where(
                m.Decision.org_id == org_id,
                m.Decision.source_document_id.is_not(None),
                m.Decision.tsv.op("@@")(func.plainto_tsquery("english", query)),
            )
        )
    ).scalars()
    docs |= {d for d in decisions if d}
    return docs


async def search(
    session: AsyncSession,
    org_id: uuid.UUID,
    query: str,
    k: int = 6,
    doc_types: list[str] | None = None,
) -> list[Hit]:
    vec = embed([query])[0].tolist()
    base = (
        select(m.DocumentChunk.id)
        .join(m.Document, m.Document.id == m.DocumentChunk.document_id)
        .where(m.DocumentChunk.org_id == org_id, m.Document.deleted_at.is_(None))
    )
    if doc_types:
        base = base.where(m.Document.type.in_(doc_types))
    vector_ids = list(
        (
            await session.execute(
                base.order_by(m.DocumentChunk.embedding.cosine_distance(vec)).limit(k * 4)
            )
        ).scalars()
    )
    tsq = func.websearch_to_tsquery("english", query)
    text_ids = list(
        (
            await session.execute(
                base.where(m.DocumentChunk.tsv.op("@@")(tsq))
                .order_by(func.ts_rank_cd(m.DocumentChunk.tsv, tsq).desc())
                .limit(k * 4)
            )
        ).scalars()
    )
    linked = await _entity_docs(session, org_id, query)
    graph_ids: list[uuid.UUID] = []
    if linked:
        graph_ids = list(
            (
                await session.execute(
                    base.where(m.DocumentChunk.document_id.in_(linked))
                    .order_by(m.DocumentChunk.embedding.cosine_distance(vec))
                    .limit(k * 2)
                )
            ).scalars()
        )
    fused = _rrf({"vector": vector_ids, "fulltext": text_ids, "graph": graph_ids})
    top = sorted(fused.items(), key=lambda kv: -kv[1][0])[:k]
    if not top:
        return []
    rows = {
        r.id: r
        for r in (
            await session.execute(
                select(
                    m.DocumentChunk.id,
                    m.DocumentChunk.document_id,
                    m.DocumentChunk.heading,
                    m.DocumentChunk.content,
                    m.Document.title,
                    m.Document.type,
                )
                .join(m.Document, m.Document.id == m.DocumentChunk.document_id)
                .where(m.DocumentChunk.id.in_([cid for cid, _ in top]))
            )
        ).all()
    }
    return [
        Hit(
            cid,
            rows[cid].document_id,
            rows[cid].title,
            rows[cid].type,
            rows[cid].heading,
            rows[cid].content,
            round(score, 5),
            srcs,
        )
        for cid, (score, srcs) in top
        if cid in rows
    ]


async def search_decisions(
    session: AsyncSession, org_id: uuid.UUID, query: str | None, limit: int = 20
) -> list[tuple[m.Decision, float]]:
    stmt = select(m.Decision).where(m.Decision.org_id == org_id, m.Decision.deleted_at.is_(None))
    if not query:
        rows = (
            (await session.execute(stmt.order_by(m.Decision.decided_at.desc()).limit(limit)))
            .scalars()
            .all()
        )
        return [(r, 0.0) for r in rows]
    tsq = func.websearch_to_tsquery("english", query)
    ft = list(
        (
            await session.execute(
                stmt.where(m.Decision.tsv.op("@@")(tsq))
                .order_by(func.ts_rank_cd(m.Decision.tsv, tsq).desc())
                .limit(limit)
            )
        ).scalars()
    )
    like = list(
        (
            await session.execute(
                stmt.where(
                    m.Decision.title.ilike(f"%{query}%") | m.Decision.rationale.ilike(f"%{query}%")
                ).limit(limit)
            )
        ).scalars()
    )
    fused = _rrf({"fulltext": [d.id for d in ft], "substring": [d.id for d in like]})
    by_id = {d.id: d for d in ft + like}
    return [(by_id[i], s) for i, (s, _) in sorted(fused.items(), key=lambda kv: -kv[1][0])][:limit]


def as_context(hits: list[Hit]) -> list[dict[str, Any]]:
    return [
        {
            "document_id": str(h.document_id),
            "title": h.title,
            "type": h.doc_type,
            "heading": h.heading,
            "content": h.content[:1200],
            "score": h.score,
            "retrieved_by": h.sources,
        }
        for h in hits
    ]
