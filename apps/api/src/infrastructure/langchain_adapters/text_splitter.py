from langchain_text_splitters import RecursiveCharacterTextSplitter


class RecursiveSplitterAdapter:
    def __init__(self, chunk_size_tokens: int, chunk_overlap_tokens: int) -> None:
        self.splitter = RecursiveCharacterTextSplitter.from_tiktoken_encoder(
            encoding_name="cl100k_base",
            chunk_size=chunk_size_tokens,
            chunk_overlap=chunk_overlap_tokens,
        )

    def split_pages(self, pages: list[dict]) -> list[dict]:
        chunks: list[dict] = []
        for page in pages:
            page_number = page.get("page_number")
            for text in self.splitter.split_text(page["text"]):
                if text.strip():
                    chunks.append({"text": text.strip(), "page_number": page_number})
        return chunks
