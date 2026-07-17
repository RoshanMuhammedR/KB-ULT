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
        chunks: list[dict] = []
        for segment in segments:
            locator = segment.get("locator")
            for text in self.splitter.split_text(segment["text"]):
                if text.strip():
                    chunks.append({"text": text.strip(), "locator": locator})
        return chunks
