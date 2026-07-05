from src.domain.entities import RetrievalResult


def build_citations(results: list[RetrievalResult]) -> list[dict]:
    return [
        {
            "asset_id": str(result.asset.id),
            "chunk_id": str(result.chunk.id),
            "filename": result.asset.filename,
            "page_number": result.chunk.metadata.get("page_number"),
            "chunk_index": result.chunk.chunk_index,
            "score": result.score,
            "excerpt": result.chunk.text[:500],
        }
        for result in results
    ]
