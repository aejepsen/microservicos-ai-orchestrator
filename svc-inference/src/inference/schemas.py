"""Schemas Pydantic v2 — subset OpenAI, espelham api/openapi.yaml."""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field


class ChatMessage(BaseModel):
    role: Literal["system", "user", "assistant"]
    content: str


class ChatCompletionRequest(BaseModel):
    model: str
    messages: list[ChatMessage] = Field(min_length=1)
    stream: bool = False
    temperature: float = 0.0
    max_tokens: int | None = None


class Usage(BaseModel):
    prompt_tokens: int
    completion_tokens: int
    total_tokens: int


class Choice(BaseModel):
    index: int
    message: ChatMessage
    finish_reason: str | None


class ChatCompletionResponse(BaseModel):
    id: str
    object: Literal["chat.completion"] = "chat.completion"
    model: str
    choices: list[Choice]
    usage: Usage


class Health(BaseModel):
    status: Literal["ok", "degraded"]
    version: str
    deps: dict[str, str]


class Metrics(BaseModel):
    source: Literal["live"] = "live"
    requests_total: int
    tokens_input_total: int
    tokens_output_total: int
    ttft_ms_p50: float
    ttft_ms_p95: float
    latency_ms_p50: float
    latency_ms_p95: float
    circuit_state: str


class BusinessError(BaseModel):
    error: str
    detail: str
    rule: str
