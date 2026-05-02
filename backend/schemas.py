"""Pydantic schemas for the Promptless AI backend."""

from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, Field, HttpUrl, field_validator


class Rect(BaseModel):
    x: float | None = None
    y: float | None = None
    width: float | None = None
    height: float | None = None
    top: float | None = None
    right: float | None = None
    bottom: float | None = None
    left: float | None = None

    model_config = {"extra": "ignore"}


class PageElement(BaseModel):
    id: int | None = None
    tag: str = ""
    text: str = ""
    href: str | None = None
    rect: Rect | dict[str, Any] | None = None

    model_config = {"extra": "ignore"}

    @field_validator("tag", "text", mode="before")
    @classmethod
    def coerce_str(cls, value: Any) -> str:
        return "" if value is None else str(value)


class RecentEvent(BaseModel):
    type: str = ""
    text: str | None = None
    tag: str | None = None
    placeholder: str | None = None
    y: float | None = None
    ts: int | float | None = None

    model_config = {"extra": "allow"}


class IntentRequest(BaseModel):
    url: str = ""
    title: str = ""
    selectedText: str = ""
    focusedElement: str = ""
    visibleText: str = ""
    viewportSummary: str = ""
    screenshotPath: str | None = None
    elements: list[PageElement] = Field(default_factory=list)
    recentEvents: list[RecentEvent] = Field(default_factory=list)

    model_config = {"extra": "allow"}

    @field_validator("url", "title", "selectedText", "focusedElement", "visibleText", "viewportSummary", mode="before")
    @classmethod
    def coerce_context_str(cls, value: Any) -> str:
        return "" if value is None else str(value)


Risk = Literal["low", "medium", "high"]


class SuggestedAction(BaseModel):
    id: str
    label: str
    description: str
    risk: Risk = "low"
    score: float = Field(default=0.0, ge=0.0, le=1.0)


class IntentResponse(BaseModel):
    traceId: str
    intent: str
    confidence: float = Field(ge=0.0, le=1.0)
    actions: list[SuggestedAction]


class ExecuteRequest(BaseModel):
    traceId: str | None = None
    actionId: str
    context: IntentRequest | None = None


class ExecuteResponse(BaseModel):
    status: Literal["done", "error"]
    result: str
    privacy: dict[str, Any] = Field(default_factory=dict)


FeedbackEvent = Literal["shown", "accepted", "dismissed", "executed", "result_closed", "thumbs_up", "thumbs_down"]


class FeedbackRequest(BaseModel):
    traceId: str | None = None
    event: FeedbackEvent
    actionId: str | None = None
    context: IntentRequest | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)
