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
) -> dict:
    return chat_service.ask(request.question)
