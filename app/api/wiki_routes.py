"""app.api.wiki_routes — thin HTTP controllers over the wiki store.

No business logic here; each endpoint validates input, delegates to the wiki
store, and maps the result to a response model. Mirrors the structure of
``routes.py`` (the routing endpoints) so the HTTP boundary stays uniform.
"""

from __future__ import annotations

from fastapi import APIRouter, Query

from app.api.schemas import (
    ExtractRequest,
    FactIn,
    FactOut,
    WikiQueryHit,
)
from app.core.wiki import Fact, extract_from_turns, get_wiki_store

router = APIRouter(prefix="/api/wiki", tags=["wiki"])


def _fact_to_out(fact: Fact) -> FactOut:
    """Map a core Fact to its API projection."""
    return FactOut(
        id=fact.id,
        subject=fact.subject,
        predicate=fact.predicate,
        object=fact.object,
        source=fact.source,
        confidence=fact.confidence,
        created_at=fact.created_at,
        tags=fact.tags,
    )


@router.get("/facts", response_model=list[FactOut])
async def list_facts(
    subject: str | None = Query(default=None, description="Filter by subject"),
) -> list[FactOut]:
    """List all facts, optionally filtered by subject."""
    store = get_wiki_store()
    return [_fact_to_out(f) for f in store.list_facts(subject)]


@router.post("/facts", response_model=FactOut, status_code=201)
async def add_fact(req: FactIn) -> FactOut:
    """Add a single manual fact. Returns the stored fact."""
    store = get_wiki_store()
    fact = Fact(
        subject=req.subject,
        predicate=req.predicate,
        object=req.object,
        source="manual",
        confidence=1.0,
        tags=req.tags,
    )
    store.add_fact(fact)  # idempotent: returns False if duplicate
    return _fact_to_out(fact)


@router.get("/query", response_model=list[WikiQueryHit])
async def query_facts(
    q: str = Query(..., min_length=1, description="Natural-language query"),
    limit: int = Query(default=5, ge=1, le=50),
) -> list[WikiQueryHit]:
    """Query the wiki for relevant facts."""
    store = get_wiki_store()
    return [
        WikiQueryHit(fact=_fact_to_out(r.fact), score=r.score)
        for r in store.query(q, limit=limit)
    ]


@router.post("/extract", response_model=list[FactOut])
async def extract_facts(req: ExtractRequest) -> list[FactOut]:
    """Extract facts from conversation turns and store them.

    Deterministic rule-based extraction (no LLM). Returns the newly added facts.
    """
    store = get_wiki_store()
    facts = extract_from_turns(req.turns, confidence=req.confidence)
    store.add_facts(facts)
    return [_fact_to_out(f) for f in facts]


@router.post("/rebuild")
async def rebuild() -> dict[str, object]:
    """Drop the in-memory index and reload from Markdown."""
    store = get_wiki_store()
    count = store.rebuild_from_markdown()
    return {"status": "rebuilt", "fact_count": count}


@router.get("/export")
async def export_wiki() -> dict[str, str]:
    """Export all wiki documents as {name: markdown} for backup/sync."""
    store = get_wiki_store()
    return store.export()
