from __future__ import annotations

from src.domain.entities import CanonicalShape, Chunk, KnowledgeAsset, shape_for_source_type
from src.infrastructure.langchain_adapters.text_splitter import RecursiveSplitterAdapter
from src.processing.chunking.regions import resolve_paged_regions, resolve_timeline_region


class RecursiveKnowledgeAssetChunker:
    def __init__(self, splitter: RecursiveSplitterAdapter) -> None:
        self.splitter = splitter

    def chunk(self, asset: KnowledgeAsset) -> list[Chunk]:
        # Handlers normalize every source into `segments` (text + a typed locator), so
        # chunking is source-agnostic: it never knows or cares whether a locator is a
        # page number or a timestamp.
        segments = asset.metadata.get("segments", [])
        split_chunks = self.splitter.split_segments(segments)

        # The shape decides which geometry resolver runs; the splitter carried the raw
        # geometry through without interpreting it. This is the single place the two meet.
        shape = shape_for_source_type(asset.source_type)

        chunks: list[Chunk] = []
        for index, split in enumerate(split_chunks):
            metadata = {
                "filename": asset.filename,
                "title": asset.title,
                "locator": split.get("locator"),
                "source_type": asset.source_type,
                "knowledge_base_id": str(asset.knowledge_base_id),
                "knowledge_asset_id": str(asset.id),
                "chunk_index": index,
            }

            regions = self._regions(shape, split)
            if regions:
                # Only written when geometry was actually recovered. Absent means "fall back
                # to the text view", which is what old rows and unrenderable sources do.
                metadata["shape"] = str(shape)
                metadata["regions"] = regions

            chunks.append(
                Chunk(
                    knowledge_asset_id=asset.id,
                    chunk_index=index,
                    text=split["text"],
                    metadata=metadata,
                )
            )
        return chunks

    @staticmethod
    def _regions(shape: CanonicalShape, split: dict) -> list[dict]:
        # None means the splitter could not locate this chunk in its segment, so there is no
        # character range to map geometry onto. The chunk still embeds and answers questions;
        # it just falls back to the text view rather than risking a misplaced highlight.
        if split.get("char_start") is None or split.get("char_end") is None:
            return []
        char_start = int(split["char_start"])
        char_end = int(split["char_end"])

        if shape is CanonicalShape.PAGED:
            spans = split.get("spans")
            if not spans:
                return []
            # The chunk's own text is a slice of the segment, so the segment text has to be
            # reconstructed to locate spans within it. `char_start` indexes into that string.
            segment_text = split.get("segment_text") or ""
            return resolve_paged_regions(spans, char_start, char_end, segment_text)

        if shape is CanonicalShape.TIMELINE:
            return resolve_timeline_region(
                split.get("region"),
                char_start,
                char_end,
                int(split.get("segment_length", 0) or 0),
            )

        return []
