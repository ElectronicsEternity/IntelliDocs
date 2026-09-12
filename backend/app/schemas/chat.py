from pydantic import BaseModel, Field


class ChatRequest(BaseModel):
    question: str = Field(min_length=1, max_length=8000)
    conversation_id: str | None = None
    top_k: int | None = Field(default=None, ge=1, le=50)


class ChatSource(BaseModel):
    document_id: str
    document_title: str | None = None
    page_number: int | None = None
    text: str


class ChatResponse(BaseModel):
    conversation_id: str
    answer: str
    sources: list[ChatSource]
