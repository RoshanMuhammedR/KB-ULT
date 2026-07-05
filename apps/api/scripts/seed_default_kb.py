from src.infrastructure.database.session import SessionLocal
from src.infrastructure.repositories import KnowledgeBaseRepository


def main() -> None:
    with SessionLocal() as db:
        kb = KnowledgeBaseRepository(db).ensure_default()
        print(f"Default KnowledgeBase ready: {kb.id}")


if __name__ == "__main__":
    main()
