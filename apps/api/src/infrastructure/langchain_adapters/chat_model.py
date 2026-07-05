from langchain_core.messages import HumanMessage, SystemMessage
from langchain_openai import ChatOpenAI


class OpenAICompatibleChatAdapter:
    def __init__(self, api_key: str, base_url: str, model: str) -> None:
        self.client = ChatOpenAI(api_key=api_key, base_url=base_url, model=model, temperature=0)

    def generate(self, messages: list[dict[str, str]]) -> str:
        converted = []
        for message in messages:
            if message["role"] == "system":
                converted.append(SystemMessage(content=message["content"]))
            else:
                converted.append(HumanMessage(content=message["content"]))
        response = self.client.invoke(converted)
        return str(response.content)
