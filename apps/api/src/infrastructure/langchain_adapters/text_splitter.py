from langchain_core.documents import Document
from langchain_text_splitters import RecursiveCharacterTextSplitter


class RecursiveSplitterAdapter:
    def __init__(self, chunk_size_tokens: int, chunk_overlap_tokens: int) -> None:
        self.splitter = RecursiveCharacterTextSplitter.from_tiktoken_encoder(
            encoding_name="cl100k_base",
            chunk_size=chunk_size_tokens,
            chunk_overlap=chunk_overlap_tokens,
        )

    def split(self, documents: list[Document]) -> list[Document]:
        """Split each document to the token budget, keeping its metadata on every piece.

        `split_documents` copies the source document's metadata onto each split, which is
        what carries the locator (page/timestamp/slide/section) through to every chunk —
        splitting never crosses a document boundary, so a citation can never straddle two
        pages.

        It does not strip or drop blanks, so that is done here: whitespace-only pieces
        would otherwise become empty chunks that cost an embedding call and can never
        match anything.
        """
        split_documents = self.splitter.split_documents(documents)
        results: list[Document] = []
        for document in split_documents:
            text = document.page_content.strip()
            if text:
                results.append(Document(page_content=text, metadata=dict(document.metadata)))
        return results
