from langchain_openai import OpenAIEmbeddings


class OpenAICompatibleEmbeddingsAdapter:
    def __init__(self, api_key: str, base_url: str, model: str) -> None:
        self.client = OpenAIEmbeddings(api_key=api_key, base_url=base_url, model=model)

    def embed_texts(self, texts: list[str]) -> list[list[float]]:
        return self.client.embed_documents(texts)

    def embed_query(self, text: str) -> list[float]:
        return self.client.embed_query(text)
