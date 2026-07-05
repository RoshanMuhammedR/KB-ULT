from typing import Annotated

from fastapi import APIRouter, Depends

from src.application.knowledge_base import KnowledgeBaseService
from src.http.dependencies import get_knowledge_base_service
from src.http.schemas.knowledge_bases import KnowledgeBaseSchema

router = APIRouter(prefix="/knowledge-bases", tags=["knowledge-bases"])


@router.get("/default", response_model=KnowledgeBaseSchema)
def get_default_knowledge_base(
    service: Annotated[KnowledgeBaseService, Depends(get_knowledge_base_service)],
) -> KnowledgeBaseSchema:
    kb = service.get_default()
    return KnowledgeBaseSchema(
        id=kb.id,
        name=kb.name,
        owner_id=kb.owner_id,
        created_at=kb.created_at,
        updated_at=kb.updated_at,
    )
