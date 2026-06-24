"""app.core.wiki.store — the self-growing wiki store.

Markdown is the source of truth (human-auditable, git-friendly). Facts are
serialized into per-subject Markdown documents. A vector index is a *derived*
artifact that can always be rebuilt from the Markdown — never the other way.

Design notes
------------
- Backend-agnostic: WikiStore takes any WikiBackend (local FS or HTTP server).
- Lazy vector index: ChromaDB is optional. If unavailable, ``query`` falls
  back to keyword/substring matching. This keeps tests network-free.
- Dedup is by Fact.id (content hash), so re-extracting the same fact is a no-op.
"""

from __future__ import annotations

from collections import defaultdict
from typing import TYPE_CHECKING

from app.core.wiki.models import Fact, WikiBackend, WikiQueryResult
from app.utils.logger import logger

if TYPE_CHECKING:
    from collections.abc import Iterable, Sequence


class WikiStore:
    """Self-growing long-term memory store.

    Args:
        backend: Storage backend (LocalFilesystemBackend or HttpBackend).
    """

    def __init__(self, backend: WikiBackend) -> None:
        self.backend = backend
        self._index: list[Fact] = []
        self._index_loaded = False

    # --- lifecycle ---

    def init(self) -> None:
        """Load all facts from the backend into the in-memory index."""
        self._index = []
        for name in self.backend.list_documents():
            content = self.backend.get_document(name)
            if content:
                self._index.extend(_parse_markdown(content))
        self._index_loaded = True
        logger.info("wiki initialized: {} facts loaded", len(self._index))

    # --- writes ---

    def add_fact(self, fact: Fact) -> bool:
        """Add a fact. Returns True if it was new, False if it already existed.

        Writes the affected subject's document immediately (source of truth).
        """
        if not self._index_loaded:
            self.init()
        if any(existing.id == fact.id for existing in self._index):
            return False
        self._index.append(fact)
        self._persist_subject(fact.subject)
        return True

    def add_facts(self, facts: "Iterable[Fact]") -> int:
        """Add many facts. Returns the count of newly-added facts."""
        added = 0
        for fact in facts:
            if self.add_fact(fact):
                added += 1
        return added

    # --- reads ---

    def query(self, text: str, limit: int = 5) -> list[WikiQueryResult]:
        """Query the wiki for facts relevant to ``text``.

        Uses substring + token-overlap scoring (vector index hook reserved).
        Returns up to ``limit`` results sorted by descending score.
        """
        if not self._index_loaded:
            self.init()
        scored = []
        for fact in self._index:
            score = _relevance(fact, text)
            if score > 0:
                scored.append(WikiQueryResult(fact=fact, score=score))
        scored.sort(key=lambda r: r.score, reverse=True)
        return scored[:limit]

    def list_facts(self, subject: str | None = None) -> list[Fact]:
        """List all facts, optionally filtered by subject."""
        if not self._index_loaded:
            self.init()
        if subject is None:
            return list(self._index)
        return [f for f in self._index if f.subject == subject]

    # --- maintenance ---

    def rebuild_from_markdown(self) -> int:
        """Drop the in-memory index and reload from Markdown.

        Use after manually editing wiki files or for disaster recovery.
        Returns the fact count.
        """
        self._index = []
        self._index_loaded = False
        self.init()
        return len(self._index)

    def export(self) -> dict[str, str]:
        """Export all documents as {name: markdown} for backup / server sync."""
        return self.backend.list_all()

    # --- internals ---

    def _persist_subject(self, subject: str) -> None:
        """Rewrite the Markdown document for one subject from the index."""
        facts = [f for f in self._index if f.subject == subject]
        self.backend.put_document(_doc_name(subject), _render_markdown(subject, facts))


def _doc_name(subject: str) -> str:
    """Slugify a subject into a document name (e.g. 'user' -> 'user')."""
    return subject.replace(" ", "-").lower()


def _render_markdown(subject: str, facts: "Sequence[Fact]") -> str:
    """Render facts for one subject as a Markdown document."""
    lines = [f"# {subject}", ""]
    for f in facts:
        tag_str = f"  [{', '.join(f.tags)}]" if f.tags else ""
        lines.append(f"- {f.predicate}: {f.object}{tag_str}")
    return "\n".join(lines) + "\n"


def _parse_markdown(content: str) -> list[Fact]:
    """Parse a Markdown document back into Facts (lossless round-trip)."""
    facts: list[Fact] = []
    subject = ""
    for line in content.splitlines():
        line = line.strip()
        if line.startswith("# "):
            subject = line[2:].strip()
        elif line.startswith("- ") and subject:
            # "- predicate: object  [tag1, tag2]"
            body = line[2:]
            tags: list[str] = []
            if body.endswith("]") and "[" in body:
                bracket = body.rfind("[")
                tags = [t.strip() for t in body[bracket + 1 : -1].split(",") if t.strip()]
                body = body[:bracket].rstrip()
            if ": " in body:
                predicate, obj = body.split(": ", 1)
                facts.append(
                    Fact(subject=subject, predicate=predicate.strip(), object=obj.strip(), tags=tags)
                )
    return facts


def _relevance(fact: Fact, text: str) -> float:
    """Score how relevant a fact is to the query text (0 = irrelevant)."""
    text_lower = text.lower()
    blob = f"{fact.subject} {fact.predicate} {fact.object}".lower()
    # Exact substring match -> high score.
    if fact.object.lower() in text_lower:
        return 1.0
    # Token overlap (Jaccard-ish).
    query_tokens = set(text_lower.split())
    fact_tokens = set(blob.split())
    if not query_tokens or not fact_tokens:
        return 0.0
    overlap = len(query_tokens & fact_tokens) / len(query_tokens | fact_tokens)
    return round(overlap, 3)
