from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends

from src.http.dependencies import get_chat_service
from src.application.chat.service import ChatService
from src.http.schemas.chat import AskQuestionRequest, AskQuestionResponse

router = APIRouter(prefix="/chat", tags=["chat"])


@router.post("/ask", response_model=AskQuestionResponse)
def ask_question(
    request: AskQuestionRequest,
    chat_service: Annotated[ChatService, Depends(get_chat_service)],
) -> AskQuestionResponse:
    # `ChatService.ask` returns a plain dict, so this is where the wire contract gets its
    # type. FastAPI would have validated it against `response_model` either way, but with
    # `-> dict` the annotation and the model disagreed and no type checker could tell.
    return AskQuestionResponse.model_validate(chat_service.ask(request.question))
