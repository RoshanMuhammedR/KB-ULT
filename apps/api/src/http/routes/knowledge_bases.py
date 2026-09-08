"""Knowledge bases: create them, list them, and say which one a request means.

Until now there was one route here — `GET /knowledge-bases/default` — and the rest of the
product resolved its base by calling `ensure_default()`, which returns *the oldest row in the
tenant*. That was fine while a tenant could only ever have one. With more than one it silently
pins everything to the first: sources upload into it, conversations belong to it, memories are
recalled from it, and a newly created base is unreachable through the entire API.

So these routes exist, and every route that acts on a base takes its id.
"""

from __future__ import annotations

from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from src.domain.entities import KnowledgeBase
from src.http.schemas.knowledge_bases import (
    CreateKnowledgeBaseRequest,
    KnowledgeBaseSchema,
    RenameKnowledgeBaseRequest,
)
from src.infrastructure.database.session import get_db
from src.infrastructure.repositories import KnowledgeAssetRepository, KnowledgeBaseRepository

router = APIRouter(prefix="/knowledge-bases", tags=["knowledge-bases"])


def _schema(kb: KnowledgeBase, counts: dict[UUID, int] | None = None) -> KnowledgeBaseSchema:
    return KnowledgeBaseSchema(
        id=kb.id,
        name=kb.name,
        created_at=kb.created_at,
        source_count=(counts or {}).get(kb.id, 0),
    )


@router.get("/default", response_model=KnowledgeBaseSchema)
async def get_default_knowledge_base(
    db: Annotated[AsyncSession, Depends(get_db)],
) -> KnowledgeBaseSchema:
    """The base a client should select when it has no preference stored.

    Kept for first-run and for clients that predate the switcher.

    Declared *before* the parameterised routes on purpose: FastAPI matches in declaration
    order, so a literal segment has to be registered ahead of `{knowledge_base_id}` or it
    gets swallowed as an id and fails UUID validation. There is no `GET /{id}` today, so
    nothing would break yet — which is exactly why it is worth pinning now rather than
    discovering it the day someone adds one.
    """
    return _schema(await KnowledgeBaseRepository(db).ensure_default())


@router.get("", response_model=list[KnowledgeBaseSchema])
async def list_knowledge_bases(
    db: Annotated[AsyncSession, Depends(get_db)],
) -> list[KnowledgeBaseSchema]:
    """Every base in this workspace, oldest first.

    Creates the first one if the tenant has none, so a new account never sees an empty
    switcher it cannot act on.
    """
    repo = KnowledgeBaseRepository(db)
    bases = await repo.list_all()
    if not bases:
        bases = [await repo.ensure_default()]

    counts = await KnowledgeAssetRepository(db).count_by_knowledge_base()
    return [_schema(base, counts) for base in bases]


@router.post("", response_model=KnowledgeBaseSchema, status_code=status.HTTP_201_CREATED)
async def create_knowledge_base(
    request: CreateKnowledgeBaseRequest,
    db: Annotated[AsyncSession, Depends(get_db)],
) -> KnowledgeBaseSchema:
    try:
        base = await KnowledgeBaseRepository(db).create(request.name)
    except ValueError as exc:
        # A duplicate name is the caller's to fix, not a server fault. 409 rather than 400:
        # the request is well-formed and conflicts with something that already exists.
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    return _schema(base)


@router.patch("/{knowledge_base_id}", response_model=KnowledgeBaseSchema)
async def rename_knowledge_base(
    knowledge_base_id: UUID,
    request: RenameKnowledgeBaseRequest,
    db: Annotated[AsyncSession, Depends(get_db)],
) -> KnowledgeBaseSchema:
    try:
        base = await KnowledgeBaseRepository(db).rename(knowledge_base_id, request.name)
    except ValueError as exc:
        # "not found" and "name taken" are both ValueError from the repository; the message
        # distinguishes them and the status should too.
        status_code = 404 if "not found" in str(exc).lower() else 409
        raise HTTPException(status_code=status_code, detail=str(exc)) from exc
    return _schema(base)


@router.delete("/{knowledge_base_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_knowledge_base(
    knowledge_base_id: UUID,
    db: Annotated[AsyncSession, Depends(get_db)],
) -> None:
    """Delete a base and everything in it — sources, conversations and memories all cascade.

    The client is expected to have said so plainly before calling. Deleting the last base is
    refused: an account with nowhere to put a source is a state the product has no screen for.
    """
    try:
        await KnowledgeBaseRepository(db).delete(knowledge_base_id)
    except ValueError as exc:
        status_code = 404 if "not found" in str(exc).lower() else 409
        raise HTTPException(status_code=status_code, detail=str(exc)) from exc
