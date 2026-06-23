"""app.api.routes — thin HTTP controllers over the routing engine.

No business logic here; each endpoint validates input, delegates to the
routing engine, and maps the result to a response model.
"""

from __future__ import annotations

from fastapi import APIRouter

from app import __version__
from app.api.schemas import (
    ExplainRequest,
    FeedbackRequest,
    HealthResponse,
    RoutingDecisionResponse,
    SignalResultOut,
)
from app.core.routing import RoutingContext, routing_engine

router = APIRouter(prefix="/api", tags=["routing"])


@router.get("/health", response_model=HealthResponse)
async def health() -> HealthResponse:
    """Liveness probe. No external dependencies checked in Stage 1."""
    return HealthResponse(status="ok", version=__version__)


@router.post("/routing/explain", response_model=RoutingDecisionResponse)
async def explain(req: ExplainRequest) -> RoutingDecisionResponse:
    """Route a message and return the full auditable decision."""
    ctx = RoutingContext(
        user_id=req.user_id,
        task_type=req.task_type,
        project_phase=req.project_phase,
        user_role=req.user_role,
    )
    decision = routing_engine.route(req.message, ctx)
    return RoutingDecisionResponse(
        tier=decision.tier,
        model=decision.model,
        score=decision.score,
        signals=[SignalResultOut(**s.__dict__) for s in decision.signal_results],
        audit_reasons=decision.audit_reasons,
        overridden=decision.overridden,
    )


@router.post("/routing/feedback")
async def feedback(req: FeedbackRequest) -> dict[str, object]:
    """Record thumb-up/down feedback for adaptive routing."""
    routing_engine.record_feedback(req.message, req.user_id, req.positive)
    return {"status": "recorded", "positive": req.positive}
