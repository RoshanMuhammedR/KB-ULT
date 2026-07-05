from src.domain.entities import KnowledgeBase
from src.infrastructure.repositories import KnowledgeBaseRepository


class KnowledgeBaseService:
    def __init__(self, kb_repo: KnowledgeBaseRepository) -> None:
        self.kb_repo = kb_repo

    def get_default(self) -> KnowledgeBase:
        return self.kb_repo.ensure_default()
