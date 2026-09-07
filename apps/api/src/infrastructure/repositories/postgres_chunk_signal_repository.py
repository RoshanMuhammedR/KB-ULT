"""Accumulated per-passage outcomes: the store behind the learned relevance prior.

**This is the one repository in the codebase that sets `tenant_id` by hand.** Everywhere else
the `before_flush` listener stamps it on new ORM objects, but that listener fires for ORM
objects only — a Core `insert()` goes straight to the database with whatever columns it was
given. `record` uses Core specifically to get `ON CONFLICT DO UPDATE`, which is what turns
"increment a counter for each of N passages" into one round trip instead of N reads and N
writes on the answer path. That trade buys latency at the cost of doing tenancy manually, so
the tenant is read from the context explicitly and the conflict target includes it.

The read path (`priors`) is an ordinary ORM `select`, so it is filtered automatically like
everything else.
"""

from __future__ import annotations

from datetime import datetime, timezone
from uuid import UUID, uuid4

from sqlalchemy import func, select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.tenant_context import current_tenant_id, current_user_id
from src.domain.entities import ChunkSignal, ChunkSignalEvent
from src.infrastructure.database.models import ChunkSignalModel
from src.infrastructure.repositories.unit_of_work import commit_or_flush


def vote_deltas(previous: int | None, current: int | None) -> tuple[int, int]:
    """`(upvoted, downvoted)` movements for a change of verdict, each in {-1, 0, +1}.

    A pure function, and separate from the statement that applies it, because this is the
    part that is easy to get wrong and worth pinning on its own. The property that matters:
    any path through the states must sum to zero when it returns to where it started, so
    up → down → retracted leaves both counters exactly as they were. Recording only the new
    verdict — "downvoted += 1" on a switch — would leave the earlier upvote standing and the
    passage would carry both at once, drifting further apart with every change of mind.
    """
    up = (1 if current == 1 else 0) - (1 if previous == 1 else 0)
    down = (1 if current == -1 else 0) - (1 if previous == -1 else 0)
    return up, down


def signal_to_domain(model: ChunkSignalModel) -> ChunkSignal:
    return ChunkSignal(
        chunk_id=model.chunk_id,
        cited=model.cited,
        supported=model.supported,
        unsupported=model.unsupported,
        upvoted=model.upvoted,
        downvoted=model.downvoted,
        last_cited_at=model.last_cited_at,
    )


class ChunkSignalRepository:
    def __init__(self, db: AsyncSession) -> None:
        self.db = db

    async def record(self, events: list[ChunkSignalEvent]) -> None:
        """Fold one answer's outcomes into the counters, in a single statement.

        Called from the post-`done` block of an answer, so it is off the latency path but
        still inside the request. An exception here is caught by the caller and logged — the
        answer was already correct without it.
        """
        if not events:
            return

        # Read once. `current_tenant_id` raises when unset, which is the intended failure:
        # a signal written without a tenant would be a row no policy can constrain.
        tenant_id = current_tenant_id()
        user_id = current_user_id()
        now = datetime.now(timezone.utc)

        rows = [
            {
                "id": uuid4(),
                "chunk_id": event.chunk_id,
                "cited": event.cited,
                "supported": event.supported,
                "unsupported": event.unsupported,
                "upvoted": 0,
                "downvoted": 0,
                "last_cited_at": now if event.cited else None,
                # Explicit, because `before_flush` never sees a Core insert. Removing these
                # two lines does not raise — it writes NULL into a NOT NULL column, or worse,
                # succeeds against a table whose policy is dormant.
                "tenant_id": tenant_id,
                "user_id": user_id,
            }
            for event in events
        ]

        statement = insert(ChunkSignalModel).values(rows)
        await self.db.execute(
            statement.on_conflict_do_update(
                # Matches `uq_chunk_signal_tenant_chunk`. Naming `tenant_id` here is what
                # makes a cross-tenant merge structurally impossible rather than merely
                # unlikely: a row carrying the wrong tenant conflicts with nothing.
                index_elements=["tenant_id", "chunk_id"],
                set_={
                    "cited": ChunkSignalModel.cited + statement.excluded.cited,
                    "supported": ChunkSignalModel.supported + statement.excluded.supported,
                    "unsupported": ChunkSignalModel.unsupported + statement.excluded.unsupported,
                    # COALESCE, not a `where=` on the statement: that clause gates the whole
                    # UPDATE, so an event carrying `supported` but no citation would silently
                    # drop every counter in the batch. This keeps the stored timestamp
                    # whenever the incoming one is NULL and touches nothing else.
                    "last_cited_at": func.coalesce(
                        statement.excluded.last_cited_at, ChunkSignalModel.last_cited_at
                    ),
                },
            )
        )
        await commit_or_flush(self.db)

    async def apply_feedback(
        self, chunk_ids: list[UUID], *, previous: int | None, current: int | None
    ) -> None:
        """Move the vote counters by the *difference* between two verdicts.

        Takes both states rather than one, because a person changing their mind has to be
        exactly reversible. See `vote_deltas`, where that arithmetic lives and is tested.
        """
        up, down = vote_deltas(previous, current)
        if not chunk_ids or (up == 0 and down == 0):
            return

        tenant_id = current_tenant_id()
        user_id = current_user_id()

        rows = [
            {
                "id": uuid4(),
                "chunk_id": chunk_id,
                "cited": 0,
                "supported": 0,
                "unsupported": 0,
                # A first-ever vote inserts the row, so the deltas double as initial values.
                # `max(0, ...)` because a retraction on a row that does not exist would
                # otherwise insert a negative count.
                "upvoted": max(0, up),
                "downvoted": max(0, down),
                "last_cited_at": None,
                "tenant_id": tenant_id,
                "user_id": user_id,
            }
            for chunk_id in chunk_ids
        ]

        statement = insert(ChunkSignalModel).values(rows)
        await self.db.execute(
            statement.on_conflict_do_update(
                index_elements=["tenant_id", "chunk_id"],
                set_={
                    "upvoted": ChunkSignalModel.upvoted + up,
                    "downvoted": ChunkSignalModel.downvoted + down,
                },
            )
        )
        await commit_or_flush(self.db)

    async def priors(self, chunk_ids: list[UUID]) -> dict[str, ChunkSignal]:
        """Signals for a retrieval pool, keyed by `str(chunk_id)`.

        Stringified keys because the caller looks them up against
        `Document.metadata[CHUNK_ID]`, which is a string. Converting here rather than at
        every call site keeps that conversion in one place.

        An ORM `select`, so `do_orm_execute` applies the tenant filter — never raw SQL.
        """
        if not chunk_ids:
            return {}
        rows = (await self.db.scalars(
            select(ChunkSignalModel).where(ChunkSignalModel.chunk_id.in_(chunk_ids))
        )).all()
        return {str(row.chunk_id): signal_to_domain(row) for row in rows}
