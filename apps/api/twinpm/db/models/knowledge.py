"""Risks, decisions, documents, feedback and themes."""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any

from pgvector.sqlalchemy import Vector
from sqlalchemy import (
    CheckConstraint,
    Computed,
    DateTime,
    Float,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
)
from sqlalchemy.dialects.postgresql import ARRAY, JSONB, TSVECTOR, UUID
from sqlalchemy.orm import Mapped, mapped_column

from twinpm.db.base import Base, SoftDeleteMixin, TenantMixin

EMBED_DIM = 384


def _fk(table: str, ondelete: str = "SET NULL", nullable: bool = True) -> Any:
    return mapped_column(
        UUID(as_uuid=True),
        ForeignKey(f"{table}.id", ondelete=ondelete),
        index=True,
        nullable=nullable,
    )


class Risk(TenantMixin, SoftDeleteMixin, Base):
    __tablename__ = "risks"
    __table_args__ = (
        CheckConstraint("probability >= 0 AND probability <= 1", name="probability"),
        CheckConstraint("impact BETWEEN 1 AND 5", name="impact"),
        CheckConstraint("status IN ('open', 'mitigating', 'closed')", name="status"),
        CheckConstraint("source IN ('model', 'manual', 'agent')", name="source"),
    )
    program_id: Mapped[uuid.UUID] = _fk("programs", "CASCADE", nullable=False)
    title: Mapped[str] = mapped_column(String(300))
    description: Mapped[str] = mapped_column(Text, default="")
    probability: Mapped[float] = mapped_column(Float)
    impact: Mapped[int] = mapped_column(Integer)
    severity: Mapped[float] = mapped_column(Float, Computed("probability * impact"))
    owner_person_id: Mapped[uuid.UUID | None] = _fk("people")
    mitigation: Mapped[str] = mapped_column(Text, default="")
    status: Mapped[str] = mapped_column(String(16), default="open")
    source: Mapped[str] = mapped_column(String(16), default="manual")
    linked_entities: Mapped[list[dict[str, Any]]] = mapped_column(JSONB, default=list)


class Document(TenantMixin, SoftDeleteMixin, Base):
    __tablename__ = "documents"
    __table_args__ = (
        CheckConstraint(
            "type IN ('design_doc', 'meeting_notes', 'prd', 'transcript', 'status_report', "
            "'other')",
            name="type",
        ),
    )
    program_id: Mapped[uuid.UUID | None] = _fk("programs", "CASCADE")
    type: Mapped[str] = mapped_column(String(32))
    title: Mapped[str] = mapped_column(String(300))
    body: Mapped[str] = mapped_column(Text)
    author_person_id: Mapped[uuid.UUID | None] = _fk("people")
    source_url: Mapped[str | None] = mapped_column(String(500))
    occurred_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class DocumentChunk(TenantMixin, Base):
    __tablename__ = "document_chunks"
    __table_args__ = (
        Index(
            "ix_document_chunks_embedding",
            "embedding",
            postgresql_using="hnsw",
            postgresql_ops={"embedding": "vector_cosine_ops"},
        ),
        Index("ix_document_chunks_tsv", "tsv", postgresql_using="gin"),
    )
    document_id: Mapped[uuid.UUID] = _fk("documents", "CASCADE", nullable=False)
    chunk_index: Mapped[int] = mapped_column(Integer)
    heading: Mapped[str] = mapped_column(String(300), default="")
    content: Mapped[str] = mapped_column(Text)
    embedding: Mapped[list[float]] = mapped_column(Vector(EMBED_DIM))
    token_count: Mapped[int] = mapped_column(Integer)
    tsv: Mapped[Any] = mapped_column(
        TSVECTOR, Computed("to_tsvector('english', heading || ' ' || content)", persisted=True)
    )


class Decision(TenantMixin, SoftDeleteMixin, Base):
    __tablename__ = "decisions"
    __table_args__ = (Index("ix_decisions_tsv", "tsv", postgresql_using="gin"),)
    program_id: Mapped[uuid.UUID] = _fk("programs", "CASCADE", nullable=False)
    title: Mapped[str] = mapped_column(String(300))
    context: Mapped[str] = mapped_column(Text, default="")
    options: Mapped[list[dict[str, Any]]] = mapped_column(JSONB, default=list)
    chosen_option: Mapped[str] = mapped_column(String(300), default="")
    rationale: Mapped[str] = mapped_column(Text, default="")
    participants: Mapped[list[uuid.UUID]] = mapped_column(ARRAY(UUID(as_uuid=True)), default=list)
    decided_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    source_document_id: Mapped[uuid.UUID | None] = _fk("documents")
    tsv: Mapped[Any] = mapped_column(
        TSVECTOR,
        Computed(
            "to_tsvector('english', title || ' ' || context || ' ' || chosen_option || ' ' "
            "|| rationale)",
            persisted=True,
        ),
    )


class Theme(TenantMixin, Base):
    __tablename__ = "themes"
    label: Mapped[str] = mapped_column(String(200))
    summary: Mapped[str] = mapped_column(Text, default="")
    size: Mapped[int] = mapped_column(Integer, default=0)
    avg_sentiment: Mapped[float] = mapped_column(Float, default=0)
    opportunity_score: Mapped[dict[str, Any]] = mapped_column(JSONB, default=dict)
    keywords: Mapped[list[str]] = mapped_column(ARRAY(String), default=list)


class FeedbackItem(TenantMixin, Base):
    __tablename__ = "feedback_items"
    __table_args__ = (
        CheckConstraint("source IN ('support', 'sales', 'survey', 'interview')", name="source"),
        Index(
            "ix_feedback_items_embedding",
            "embedding",
            postgresql_using="hnsw",
            postgresql_ops={"embedding": "vector_cosine_ops"},
        ),
    )
    source: Mapped[str] = mapped_column(String(16))
    customer_segment: Mapped[str] = mapped_column(String(32))
    text: Mapped[str] = mapped_column(Text)
    sentiment: Mapped[float] = mapped_column(Float)
    theme_id: Mapped[uuid.UUID | None] = _fk("themes")
    received_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)
    embedding: Mapped[list[float] | None] = mapped_column(Vector(EMBED_DIM))
