from typing import Literal
from pydantic import BaseModel, Field, field_validator


class AskRequest(BaseModel):
    question: str = Field(min_length=1, max_length=1000)
    conversation_id: int | None = None        # leave out to start a new chat

    @field_validator("question")
    @classmethod
    def not_blank(cls, v: str) -> str:
        v = v.strip()
        if not v:
            raise ValueError("question cannot be empty")
        return v


class GoogleHealthTokens(BaseModel):
    refresh_token: str = Field(min_length=1, max_length=2048)
    scope: str = Field(max_length=4096)       # space-separated, exactly as Google returned it


class Source(BaseModel):
    n: int
    title: str
    page: int | None
    url: str | None


class ToolCall(BaseModel):
    tool: str
    args: dict


class AskResponse(BaseModel):
    answer: str
    sources: list[Source]
    safety: Literal["ok", "red_flag"]
    conversation_id: int
    tool_calls: list[ToolCall]
    latency_ms: int