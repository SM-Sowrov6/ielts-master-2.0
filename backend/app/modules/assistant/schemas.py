"""Assistant request/response bodies. Limits here are the first line of request validation."""

from typing import Literal, Self

from pydantic import BaseModel, ConfigDict, Field, model_validator

MAX_MESSAGES = 20
MAX_CHARS = 2000


class MessageIn(BaseModel):
    model_config = ConfigDict(extra="forbid")

    role: Literal["user", "assistant"]
    content: str = Field(min_length=1, max_length=MAX_CHARS * 2)


class PageIn(BaseModel):
    """Only the path is accepted; the server maps it to a curated description."""

    model_config = ConfigDict(extra="forbid")

    path: str = Field(min_length=1, max_length=300, pattern=r"^/")


class ChatIn(BaseModel):
    model_config = ConfigDict(extra="forbid")

    messages: list[MessageIn] = Field(min_length=1, max_length=MAX_MESSAGES)
    page: PageIn | None = None

    @model_validator(mode="after")
    def _ends_with_user(self) -> Self:
        last = self.messages[-1]
        if last.role != "user":
            raise ValueError("The last message must be from the user")
        if not last.content.strip():
            raise ValueError("The message is empty")
        if len(last.content) > MAX_CHARS:
            raise ValueError(f"Messages are limited to {MAX_CHARS} characters")
        return self


class ChatOut(BaseModel):
    role: Literal["assistant"] = "assistant"
    content: str


class StatusOut(BaseModel):
    available: bool
