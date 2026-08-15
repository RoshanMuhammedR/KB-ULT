from langchain_text_splitters import RecursiveCharacterTextSplitter


class RecursiveSplitterAdapter:
    def __init__(self, chunk_size_tokens: int, chunk_overlap_tokens: int) -> None:
        self.splitter = RecursiveCharacterTextSplitter.from_tiktoken_encoder(
            encoding_name="cl100k_base",
            chunk_size=chunk_size_tokens,
            chunk_overlap=chunk_overlap_tokens,
        )

    def split_segments(self, segments: list[dict]) -> list[dict]:
        # Split each source segment's text, carrying that segment's locator onto every
        # resulting chunk. The locator is opaque here (page for PDF, timestamp/section
        # for other sources later) — the splitter never inspects it.
        #
        # `spans`/`region` ride along untouched too, paired with the chunk's character range
        # so the chunker can resolve them into highlight regions. This layer stays ignorant
        # of what they mean.
        chunks: list[dict] = []
        for segment in segments:
            locator = segment.get("locator")
            text = segment.get("text") or ""
            cursor = 0
            for piece in self.splitter.split_text(text):
                if not piece.strip():
                    continue
                # Offsets are resolved here rather than via LangChain's `add_start_index`.
                # That option re-locates each chunk with a single `find` from position 0,
                # which returns -1 whenever the splitter's internal re-join normalised
                # whitespace differently from the source — measured at 4 of 9 chunks on
                # ordinary prose, and a -1 would silently place a highlight at the wrong
                # end of the page. Searching forward from the previous match instead is
                # both correct for repeated text and robust to a miss.
                start = text.find(piece, cursor)
                if start < 0:
                    start = text.find(piece)
                if start < 0:
                    # Reassembled beyond recognition: keep the chunk (it still embeds and
                    # answers questions), just without geometry. A missing highlight beats
                    # a wrong one.
                    chunks.append(self._chunk(piece, locator, None, None, segment, text))
                    continue
                cursor = start + len(piece)
                chunks.append(
                    self._chunk(piece, locator, start, start + len(piece), segment, text)
                )
        return chunks

    @staticmethod
    def _chunk(
        piece: str,
        locator: dict | None,
        char_start: int | None,
        char_end: int | None,
        segment: dict,
        segment_text: str,
    ) -> dict:
        return {
            "text": piece,
            "locator": locator,
            "char_start": char_start,
            "char_end": char_end,
            "spans": segment.get("spans"),
            "region": segment.get("region"),
            # The offsets above are meaningless without the string they index into, so it
            # travels with them rather than being re-derived later.
            "segment_text": segment_text,
            "segment_length": len(segment_text),
        }
