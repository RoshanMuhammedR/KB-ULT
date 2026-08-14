from __future__ import annotations

from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from src.core.text import sanitize_text_for_storage
from src.domain.entities import Conversation, Message, MessageRole
from src.infrastructure.database.models import ConversationModel, MessageModel
from src.infrastructure.repositories.mappers import conversation_to_domain, message_to_domain


class ConversationRepository:
    """Persistence for chat threads.

    Every read goes through `select().where(id == ...)` rather than `Session.get()` — the
    same deliberate choice `KnowledgeAssetRepository` makes, because `Session.get()` can
    return an identity-map hit that never went through the tenant filter.
    """

    def __init__(self, db: Session) -> None:
        self.db = db

    # --- Reads --------------------------------------------------------------------

    def list_for_knowledge_base(self, knowledge_base_id: UUID) -> list[tuple[Conversation, int, str]]:
        """Return `[(conversation, message_count, preview)]`, most recently touched first.

        Counts and previews are computed in SQL so the list view never loads whole threads.
        """
        models = self.db.scalars(
            select(ConversationModel)
            .where(ConversationModel.knowledge_base_id == knowledge_base_id)
            .order_by(ConversationModel.updated_at.desc())
        ).all()
        if not models:
            return []

        ids = [model.id for model in models]

        counts = dict(
            self.db.execute(
                select(MessageModel.conversation_id, func.count(MessageModel.id))
                .where(MessageModel.conversation_id.in_(ids))
                .group_by(MessageModel.conversation_id)
            ).all()
        )

        # The most recent message in each thread is what the list previews.
        latest_ts = (
            select(
                MessageModel.conversation_id.label("conversation_id"),
                func.max(MessageModel.created_at).label("created_at"),
            )
            .where(MessageModel.conversation_id.in_(ids))
            .group_by(MessageModel.conversation_id)
            .subquery()
        )
        previews = dict(
            self.db.execute(
                select(MessageModel.conversation_id, MessageModel.content).join(
                    latest_ts,
                    (MessageModel.conversation_id == latest_ts.c.conversation_id)
                    & (MessageModel.created_at == latest_ts.c.created_at),
                )
            ).all()
        )

        return [
            (
                conversation_to_domain(model),
                int(counts.get(model.id, 0)),
                (previews.get(model.id) or "")[:160],
            )
            for model in models
        ]

    def get(self, conversation_id: UUID) -> Conversation | None:
        model = self._model(conversation_id)
        return conversation_to_domain(model) if model is not None else None

    def get_with_messages(self, conversation_id: UUID) -> Conversation | None:
        model = self._model(conversation_id)
        if model is None:
            return None
        messages = self.db.scalars(
            select(MessageModel)
            .where(MessageModel.conversation_id == conversation_id)
            .order_by(MessageModel.created_at.asc())
        ).all()
        return conversation_to_domain(model, list(messages))

    def recent_messages(self, conversation_id: UUID, limit: int) -> list[Message]:
        """The tail of a thread, oldest-first — what follow-up questions are built from."""
        models = self.db.scalars(
            select(MessageModel)
            .where(MessageModel.conversation_id == conversation_id)
            .order_by(MessageModel.created_at.desc())
            .limit(limit)
        ).all()
        return [message_to_domain(model) for model in reversed(models)]

    def find_by_cited_asset(self, asset_id: UUID) -> list[tuple[UUID, str, dict]]:
        """Return `[(conversation_id, conversation_title, citation)]` for one source.

        Uses JSONB containment against the `ix_messages_citations` GIN index, so this stays
        cheap as the message table grows.
        """
        rows = self.db.execute(
            select(MessageModel.conversation_id, ConversationModel.title, MessageModel.citations)
            .join(ConversationModel, ConversationModel.id == MessageModel.conversation_id)
            .where(MessageModel.citations.contains([{"asset_id": str(asset_id)}]))
            .order_by(MessageModel.created_at.desc())
        ).all()

        results: list[tuple[UUID, str, dict]] = []
        for conversation_id, title, citations in rows:
            for citation in citations or []:
                if citation.get("asset_id") == str(asset_id):
                    results.append((conversation_id, title, citation))
        return results

    # --- Writes -------------------------------------------------------------------

    def create(self, conversation: Conversation) -> Conversation:
        model = ConversationModel(
            id=conversation.id,
            knowledge_base_id=conversation.knowledge_base_id,
            title=sanitize_text_for_storage(conversation.title),
        )
        self.db.add(model)
        self._commit()
        self.db.refresh(model)
        return conversation_to_domain(model)

    def rename(self, conversation_id: UUID, title: str) -> Conversation:
        model = self._model(conversation_id)
        if model is None:
            raise ValueError("Conversation not found")
        cleaned = sanitize_text_for_storage(title).strip()
        if not cleaned:
            raise ValueError("A conversation needs a title")
        model.title = cleaned
        self._commit()
        self.db.refresh(model)
        return conversation_to_domain(model)

    def delete(self, conversation_id: UUID) -> None:
        model = self._model(conversation_id)
        if model is None:
            raise ValueError("Conversation not found")
        # Messages go with it via the FK's ON DELETE CASCADE.
        self.db.delete(model)
        self._commit()

    def append_message(self, message: Message) -> Message:
        model = MessageModel(
            id=message.id,
            conversation_id=message.conversation_id,
            role=MessageRole(message.role).value,
            content=sanitize_text_for_storage(message.content),
            citations=message.citations or [],
            insufficient_context=message.insufficient_context,
        )
        self.db.add(model)

        # Appending is what "last touched" means, so the thread rises in the list.
        conversation = self._model(message.conversation_id)
        if conversation is not None:
            conversation.updated_at = func.now()

        self._commit()
        self.db.refresh(model)
        return message_to_domain(model)

    def delete_message(self, conversation_id: UUID, message_id: UUID) -> None:
        model = self.db.scalars(
            select(MessageModel).where(
                MessageModel.id == message_id,
                MessageModel.conversation_id == conversation_id,
            )
        ).first()
        if model is None:
            raise ValueError("Message not found")
        self.db.delete(model)
        self._commit()

    # --- Internals ----------------------------------------------------------------

    def _model(self, conversation_id: UUID) -> ConversationModel | None:
        return self.db.scalars(
            select(ConversationModel).where(ConversationModel.id == conversation_id)
        ).first()

    def _commit(self) -> None:
        try:
            self.db.commit()
        except Exception:
            self.db.rollback()
            raise
