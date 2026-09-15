from pydantic import BaseModel, Field


class ChatRequest(BaseModel):
    question: str = Field(min_length=1, max_length=8000)
    conversation_id: str | None = None
    top_k: int | None = Field(default=None, ge=1, le=50)


class ChatTableField(BaseModel):
    value: str
    row_start: int
    row_end: int
    column_start: int
    column_end: int


class ChatTable(BaseModel):
    table_number: int
    page_numbers: list[int]
    fields: list[ChatTableField]


class ChatSource(BaseModel):
    document_id: str
    document_title: str | None = None
    page_number: int | None = None
    text: str
    content_type: str = "text"
    table: ChatTable | None = None


class ChatResponse(BaseModel):
    conversation_id: str
    answer: str
    sources: list[ChatSource]
