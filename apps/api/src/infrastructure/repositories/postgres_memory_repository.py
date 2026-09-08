"""Workspace memories: what this library has been told about itself.

Lexical search over the `fts` generated column, the same mechanism `chunks` uses. No vectors:
memories are one-sentence facts in the user's own vocabulary, `QueryResolver` already produces
keywords for exactly this kind of matching, and a vector column would couple memory to
`embedding_dimensions` — meaning a model change would require re-embedding memories as well as
the corpus, for a table that holds tens of rows.
"""

from __future__ import annotations

import operator
import re
from datetime import datetime, timezone
from functools import reduce
from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.tenant_context import current_user_id
from src.core.text import sanitize_text_for_storage
from src.domain.entities import Memory, MemoryKind
from src.infrastructure.database.models import WorkspaceMemoryModel
from src.infrastructure.repositories.unit_of_work import commit_or_flush


def memory_to_domain(model: WorkspaceMemoryModel) -> Memory:
    return Memory(
        id=model.id,
        knowledge_base_id=model.knowledge_base_id,
        content=model.content,
        kind=MemoryKind(model.kind),
        source_conversation_id=model.source_conversation_id,
        source_message_id=model.source_message_id,
        superseded_by=model.superseded_by,
        superseded_at=model.superseded_at,
        last_used_at=model.last_used_at,
        created_at=model.created_at,
    )


class MemoryRepository:
    def __init__(self, db: AsyncSession) -> None:
        self.db = db

    def _visible(self, statement):
        """Facts belong to the workspace; preferences belong to the person who stated them.

        Not redundant with the automatic tenant filter, which covers the tenant and stops
        there. "Answer briefly" is one person's way of working, and imposing it on a
        teammate's answers would be a bug that only appears once a workspace has two people
        in it — by which point nobody would think to look here.
        """
        return statement.where(
            (WorkspaceMemoryModel.kind == MemoryKind.FACT.value)
            | (WorkspaceMemoryModel.user_id == current_user_id())
        )

    async def list_active(self, knowledge_base_id: UUID) -> list[Memory]:
        rows = (await self.db.scalars(
            self._visible(
                select(WorkspaceMemoryModel).where(
                    WorkspaceMemoryModel.knowledge_base_id == knowledge_base_id,
                    WorkspaceMemoryModel.superseded_at.is_(None),
                )
            ).order_by(WorkspaceMemoryModel.created_at.desc())
        )).all()
        return [memory_to_domain(row) for row in rows]

    async def list_all(self, knowledge_base_id: UUID) -> list[Memory]:
        """Including superseded ones — the record of what the workspace used to believe."""
        rows = (await self.db.scalars(
            self._visible(
                select(WorkspaceMemoryModel).where(
                    WorkspaceMemoryModel.knowledge_base_id == knowledge_base_id
                )
            ).order_by(WorkspaceMemoryModel.created_at.desc())
        )).all()
        return [memory_to_domain(row) for row in rows]

    async def search(self, knowledge_base_id: UUID, query: str, limit: int) -> list[Memory]:
        """Active memories matching any of a query's terms, best first.

        **OR, not AND, and that is the whole point.** This used `websearch_to_tsquery`, which
        ANDs its terms — copied from the lexical retrieval arm, where ANDing is right because
        a passage is long and a query that matches every term in one passage is a strong
        signal. A memory is one sentence of at most `memory_max_chars`. Requiring every word
        of "Which database stores the trips, and why was that one chosen?" to appear in a
        300-character fact means nothing ever matches, and the whole feature silently returns
        nothing on every turn.

        It is worse than it looks, because the query is frequently the entire question:
        `QueryResolver` returns `keywords = question` verbatim whenever there is no history
        (`retrieval/langchain/query.py`), which is every opening turn.

        `plainto_tsquery` normalises and stems the same way but is still an AND, so the terms
        are ORed explicitly. Ranking by `ts_rank_cd` then does the discriminating: a memory
        matching three query terms outranks one matching a single stopword-ish term, and
        `limit` keeps the tail out. Precision comes from the ranking, not from the filter.
        """
        terms = [term for term in re.findall(r"[\w']+", query.lower()) if len(term) > 2]
        if not terms:
            return []

        # `||` is tsquery OR, and it has to be the SQL operator rather than Python's `|`:
        # `operator.or_` on SQLAlchemy elements renders a *boolean* OR, which yields
        # `fts @@ q1 OR q2 OR q3` — the `@@` binds to the first term only and Postgres
        # rejects the bare tsqueries that follow.
        #
        # Each term goes through `plainto_tsquery` so stemming and stop-word removal match
        # how `fts` was generated. Composing tsquery *values* rather than building a query
        # string also means user text never becomes query syntax.
        tsquery = reduce(
            lambda left, right: left.op("||")(right),
            (func.plainto_tsquery("english", term) for term in terms),
        )
        rows = (await self.db.scalars(
            self._visible(
                select(WorkspaceMemoryModel).where(
                    WorkspaceMemoryModel.knowledge_base_id == knowledge_base_id,
                    WorkspaceMemoryModel.superseded_at.is_(None),
                    WorkspaceMemoryModel.fts.op("@@")(tsquery),
                )
            )
            .order_by(func.ts_rank_cd(WorkspaceMemoryModel.fts, tsquery).desc())
            .limit(limit)
        )).all()
        return [memory_to_domain(row) for row in rows]

    async def get(self, memory_id: UUID) -> Memory | None:
        model = await self._model(memory_id)
        return memory_to_domain(model) if model else None

    async def create(self, memory: Memory) -> Memory:
        model = WorkspaceMemoryModel(
            id=memory.id,
            knowledge_base_id=memory.knowledge_base_id,
            content=sanitize_text_for_storage(memory.content),
            kind=MemoryKind(memory.kind).value,
            source_conversation_id=memory.source_conversation_id,
            source_message_id=memory.source_message_id,
        )
        self.db.add(model)
        await commit_or_flush(self.db)
        await self.db.refresh(model)
        return memory_to_domain(model)

    async def update_content(self, memory_id: UUID, content: str) -> Memory:
        model = await self._model(memory_id)
        if model is None:
            raise ValueError("Memory not found")
        model.content = sanitize_text_for_storage(content)
        await commit_or_flush(self.db)
        await self.db.refresh(model)
        return memory_to_domain(model)

    async def supersede(self, memory_id: UUID, replacement_id: UUID) -> None:
        """Retire a memory in favour of a newer one, without destroying it.

        The old row stays readable, so "why does it think that?" has an answer. Only the
        `superseded_at IS NULL` filter on the read path decides what is currently believed.
        """
        model = await self._model(memory_id)
        if model is None:
            return
        model.superseded_by = replacement_id
        model.superseded_at = datetime.now(timezone.utc)
        await commit_or_flush(self.db)

    async def touch(self, memory_ids: list[UUID]) -> None:
        """Mark memories as used, so a stale one is visibly stale in the UI."""
        if not memory_ids:
            return
        rows = (await self.db.scalars(
            select(WorkspaceMemoryModel).where(WorkspaceMemoryModel.id.in_(memory_ids))
        )).all()
        now = datetime.now(timezone.utc)
        for row in rows:
            row.last_used_at = now
        await commit_or_flush(self.db)

    async def delete(self, memory_id: UUID) -> None:
        """A hard delete. "Forget this" has to actually forget, or the feature is a lie."""
        model = await self._model(memory_id)
        if model is None:
            raise ValueError("Memory not found")
        await self.db.delete(model)
        await commit_or_flush(self.db)

    async def delete_all(self, knowledge_base_id: UUID) -> int:
        """Forget everything. Returns how many were forgotten, so the UI can say so."""
        rows = (await self.db.scalars(
            self._visible(
                select(WorkspaceMemoryModel).where(
                    WorkspaceMemoryModel.knowledge_base_id == knowledge_base_id
                )
            )
        )).all()
        for row in rows:
            await self.db.delete(row)
        await commit_or_flush(self.db)
        return len(rows)

    async def _model(self, memory_id: UUID) -> WorkspaceMemoryModel | None:
        # `select`, never `Session.get` — an identity-map hit would skip the tenant filter.
        return (await self.db.scalars(
            select(WorkspaceMemoryModel).where(WorkspaceMemoryModel.id == memory_id)
        )).first()
