"""One reader's verdict on one answer.

**Every read here filters `user_id` explicitly.** The `do_orm_execute` listener injects a
tenant filter and nothing else — `user_id` is stamped on write by `before_flush` but is never
part of the automatic predicate. For most tables that is exactly right, because the corpus and
its conversations belong to the workspace. Feedback does not: "did *you* rate this answer" is
a per-person question, and inheriting only the tenant filter would show one teammate another's
thumb and let a retraction move someone else's row.

The write methods return the *previous* rating, because the counters in `chunk_signals` move
by the difference between two verdicts rather than by the new one. See
`ChunkSignalRepository.apply_feedback`.
"""

from __future__ import annotations

from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.tenant_context import current_user_id
from src.infrastructure.database.models import MessageFeedbackModel
from src.infrastructure.repositories.unit_of_work import commit_or_flush


class MessageFeedbackRepository:
    def __init__(self, db: AsyncSession) -> None:
        self.db = db

    async def set(self, message_id: UUID, rating: int) -> int | None:
        """Record this user's verdict, returning whatever it replaced.

        Upsert by hand rather than `ON CONFLICT`: the previous value has to be read anyway
        to compute the counter delta, so a conflict clause would save nothing and would cost
        the automatic tenant stamping that an ORM write gets for free.
        """
        model = await self._own(message_id)
        if model is None:
            self.db.add(MessageFeedbackModel(message_id=message_id, rating=rating))
            await commit_or_flush(self.db)
            return None

        previous = model.rating
        model.rating = rating
        await commit_or_flush(self.db)
        return previous

    async def clear(self, message_id: UUID) -> int | None:
        """Retract this user's verdict. Returns what was retracted, or None if there was none."""
        model = await self._own(message_id)
        if model is None:
            return None
        previous = model.rating
        await self.db.delete(model)
        await commit_or_flush(self.db)
        return previous

    async def ratings_for(self, message_ids: list[UUID]) -> dict[UUID, int]:
        """This user's ratings across a thread, in one statement.

        Batched for the same reason `list_for_knowledge_base` batches its counts: loading a
        conversation should not issue one query per message.
        """
        if not message_ids:
            return {}
        rows = (await self.db.scalars(
            select(MessageFeedbackModel).where(
                MessageFeedbackModel.message_id.in_(message_ids),
                MessageFeedbackModel.user_id == current_user_id(),
            )
        )).all()
        return {row.message_id: row.rating for row in rows}

    async def _own(self, message_id: UUID) -> MessageFeedbackModel | None:
        return (await self.db.scalars(
            select(MessageFeedbackModel).where(
                MessageFeedbackModel.message_id == message_id,
                # Not redundant with the tenant filter: two users in one workspace each have
                # their own row for the same message.
                MessageFeedbackModel.user_id == current_user_id(),
            )
        )).first()
