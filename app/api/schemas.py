"""app.api.schemas — Pydantic request/response models for the API layer.

Thin models that mirror the core dataclasses so the HTTP boundary stays
explicit and validated. No business logic lives here.
"""

from __future__ import annotations

from pydantic import BaseModel, Field

from app.core.routing.tiers import Tier


class SignalResultOut(BaseModel):
    """One signal's contribution to a routing decision (audit)."""

    name: str
    raw: float
    contribution: float
    note: str = ""


class ExplainRequest(BaseModel):
    """Request body for POST /api/routing/explain."""

    message: str = Field(..., min_length=1, max_length=8000, description="User message to route")
    user_id: str | None = Field(default=None, description="Stable user id for feedback")
    task_type: str | None = Field(default=None, description="Coarse task category")
    project_phase: str | None = Field(default=None, description="Current project phase")
    user_role: str | None = Field(default=None, description="User role")


class RoutingDecisionResponse(BaseModel):
    """Response for POST /api/routing/explain."""

    tier: Tier
    model: str
    score: float
    signals: list[SignalResultOut]
    audit_reasons: list[str]
    overridden: bool


class FeedbackRequest(BaseModel):
    """Request body for POST /api/routing/feedback."""

    message: str = Field(..., min_length=1, max_length=8000)
    user_id: str | None = None
    positive: bool


class HealthResponse(BaseModel):
    """Response for GET /api/health."""

    status: str
    version: str
