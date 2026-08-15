from src.domain.entities import RetrievalResult


def build_citations(results: list[RetrievalResult]) -> list[dict]:
    # `locator` is the source-neutral position (PDF: {type:"page", value:N}); the
    # frontend renders it per `source_type`. This replaces the old PDF-only
    # `page_number` so web/YouTube citations need no shape change here.
    return [
        {
            "asset_id": str(result.asset.id),
            "chunk_id": str(result.chunk.id),
            "filename": result.asset.filename,
            "source_type": result.asset.source_type,
            "locator": result.chunk.metadata.get("locator"),
            "chunk_index": result.chunk.chunk_index,
            "score": result.score,
            "excerpt": result.chunk.text[:500],
        }
        for result in results
    ]
