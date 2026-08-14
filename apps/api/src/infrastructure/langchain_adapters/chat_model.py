from __future__ import annotations

from typing import Iterator

from langchain_core.messages import AIMessage, BaseMessage, HumanMessage, SystemMessage
from langchain_openai import ChatOpenAI


class OpenAICompatibleChatAdapter:
    def __init__(self, api_key: str, base_url: str, model: str) -> None:
        self.client = ChatOpenAI(api_key=api_key, base_url=base_url, model=model, temperature=0)

    def generate(self, messages: list[dict[str, str]]) -> str:
        response = self.client.invoke(self._convert(messages))
        return str(response.content)

    def stream(self, messages: list[dict[str, str]]) -> Iterator[str]:
        """Yield the answer in pieces as the model produces them.

        `generate` is unchanged and still backs the non-streaming /chat/ask endpoint; this
        is what the SSE route consumes so a long answer is legible while it is being written.
        """
        for chunk in self.client.stream(self._convert(messages)):
            text = chunk.content
            if not text:
                continue
            # Some gateways return content as a list of parts rather than a string.
            if isinstance(text, list):
                text = "".join(
                    part.get("text", "") for part in text if isinstance(part, dict)
                )
            if text:
                yield str(text)

    @staticmethod
    def _convert(messages: list[dict[str, str]]) -> list[BaseMessage]:
        # Prior assistant turns must map to AIMessage, not HumanMessage — otherwise a
        # follow-up reads as though the user said the previous answer themselves.
        converted: list[BaseMessage] = []
        for message in messages:
            role = message["role"]
            if role == "system":
                converted.append(SystemMessage(content=message["content"]))
            elif role == "assistant":
                converted.append(AIMessage(content=message["content"]))
            else:
                converted.append(HumanMessage(content=message["content"]))
        return converted
