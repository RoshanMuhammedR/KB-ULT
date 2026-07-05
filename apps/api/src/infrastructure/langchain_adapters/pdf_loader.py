from io import BytesIO

from pypdf import PdfReader


class PdfLoaderAdapter:
    def load_pages(self, file_data: bytes) -> list[dict]:
        reader = PdfReader(BytesIO(file_data))
        title = None
        if reader.metadata and reader.metadata.title:
            title = str(reader.metadata.title)

        pages = []
        for index, page in enumerate(reader.pages):
            pages.append(
                {
                    "text": page.extract_text() or "",
                    "metadata": {"page": index, "title": title},
                }
            )
        return pages
