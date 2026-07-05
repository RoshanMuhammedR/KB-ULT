from src.domain.entities import KnowledgeBase
from src.infrastructure.repositories import KnowledgeBaseRepository


def get_default_knowledge_base(kb_repo: KnowledgeBaseRepository) -> KnowledgeBase:
    return kb_repo.ensure_default()
