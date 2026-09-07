"""What the workspace remembers, and the controls that make that acceptable.

A system that silently accumulates facts about you and injects them into every future answer
is not a feature, it is something that happens to you. The difference is entirely in these
routes: being able to see what was learned, correct it, and delete it. `DELETE` is a hard
delete for the same reason — "forget this" that only hides a row is a lie the user cannot
detect.
"""

from __future__ import annotations

from typing import Annotated, Literal
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from src.domain.entities import Memory, MemoryKind
from src.http.schemas.memories import MemorySchema
from src.infrastructure.database.session import get_db
from src.infrastructure.repositories import KnowledgeBaseRepository, MemoryRepository

router = APIRouter(prefix="/memories", tags=["memories"])


class CreateMemoryRequest(BaseModel):
    content: str
    kind: Literal["fact", "preference"] = "fact"


class UpdateMemoryRequest(BaseModel):
    content: str


def _schema(memory: Memory) -> MemorySchema:
    return MemorySchema(
        id=memory.id,
        content=memory.content,
        kind=memory.kind.value,
        source_conversation_id=memory.source_conversation_id,
        superseded_at=memory.superseded_at,
        last_used_at=memory.last_used_at,
        created_at=memory.created_at,
    )


@router.get("", response_model=list[MemorySchema])
async def list_memories(
    db: Annotated[AsyncSession, Depends(get_db)],
    include_superseded: bool = False,
) -> list[MemorySchema]:
    """What the workspace currently believes. Corrected memories are kept but hidden.

    Superseded rows stay behind a flag rather than being dropped: they answer "why did it
    think that?", which is the question a surprising answer provokes.
    """
    kb = await KnowledgeBaseRepository(db).ensure_default()
    repo = MemoryRepository(db)
    memories = (
        await repo.list_all(kb.id) if include_superseded else await repo.list_active(kb.id)
    )
    return [_schema(memory) for memory in memories]


@router.post("", response_model=MemorySchema, status_code=status.HTTP_201_CREATED)
async def create_memory(
    request: CreateMemoryRequest,
    db: Annotated[AsyncSession, Depends(get_db)],
) -> MemorySchema:
    """Tell the workspace something directly, without waiting for it to be inferred."""
    content = request.content.strip()
    if not content:
        raise HTTPException(status_code=422, detail="A memory needs some content")

    kb = await KnowledgeBaseRepository(db).ensure_default()
    memory = await MemoryRepository(db).create(
        Memory(knowledge_base_id=kb.id, content=content, kind=MemoryKind(request.kind))
    )
    return _schema(memory)


@router.patch("/{memory_id}", response_model=MemorySchema)
async def update_memory(
    memory_id: UUID,
    request: UpdateMemoryRequest,
    db: Annotated[AsyncSession, Depends(get_db)],
) -> MemorySchema:
    """Correct a memory in place. A wrong remembered fact is worse than no memory at all,
    because it is applied to questions it has nothing to do with."""
    content = request.content.strip()
    if not content:
        raise HTTPException(status_code=422, detail="A memory needs some content")

    try:
        memory = await MemoryRepository(db).update_content(memory_id, content)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    return _schema(memory)


@router.delete("/{memory_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_memory(
    memory_id: UUID,
    db: Annotated[AsyncSession, Depends(get_db)],
) -> None:
    try:
        await MemoryRepository(db).delete(memory_id)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.delete("", status_code=status.HTTP_204_NO_CONTENT)
async def forget_everything(db: Annotated[AsyncSession, Depends(get_db)]) -> None:
    """Clear the whole memory. Destructive and immediate, which is the point."""
    kb = await KnowledgeBaseRepository(db).ensure_default()
    await MemoryRepository(db).delete_all(kb.id)
