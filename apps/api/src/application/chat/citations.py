from src.domain.entities import RetrievalResult


def build_citations(results: list[RetrievalResult]) -> list[dict]:
    # `locator` is the source-neutral position (PDF: {type:"page", value:N}); the
    # frontend renders it per `source_type`. This replaces the old PDF-only
    # `page_number` so web/YouTube citations need no shape change here.
    # `shape`/`regions` are optional and only present when the pipeline recovered geometry
    # for that chunk. Old rows have neither, so the viewer falls back to the text view —
    # which is why they are added rather than folded into `locator`, whose {type,value} shape
    # is depended on by `formatLocator` across both frontends.
    citations = []
    for result in results:
        citation = {
            "asset_id": str(result.asset.id),
            "chunk_id": str(result.chunk.id),
            "filename": result.asset.filename,
            "source_type": result.asset.source_type,
            "locator": result.chunk.metadata.get("locator"),
            "chunk_index": result.chunk.chunk_index,
            "score": result.score,
            "excerpt": result.chunk.text[:500],
        }
        shape = result.chunk.metadata.get("shape")
        regions = result.chunk.metadata.get("regions")
        if shape and regions:
            citation["shape"] = shape
            citation["regions"] = regions
        citations.append(citation)
    return citations
