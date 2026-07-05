from __future__ import annotations

from pydantic import BaseModel, Field


class AskQuestionRequest(BaseModel):
    question: str = Field(min_length=1)


class CitationSchema(BaseModel):
    asset_id: str
    chunk_id: str
    filename: str
    page_number: int | None
    chunk_index: int
    score: float
    excerpt: str


class AskQuestionResponse(BaseModel):
    answer: str
    insufficient_context: bool
    citations: list[CitationSchema]
