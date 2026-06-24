"""app.core.wiki.models — wiki data models (no logic, no I/O).

Holds the Fact dataclass and the WikiBackend protocol. Keeping these here
breaks potential cycles and makes the backend abstraction the explicit
contract that local and server-deploy backends must satisfy.
"""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from typing import Protocol


@dataclass
class Fact:
    """A single permanent fact stored in the wiki.

    Facts are the unit of long-term memory. They are deduplicated by a stable
    content hash so the same fact is never stored twice.

    Attributes:
        id: Stable hash of (subject + predicate + object); used for dedup.
        subject: What the fact is about (e.g. "user", "project:aether").
        predicate: The relationship/attribute (e.g. "prefers", "uses").
        object: The value (e.g. "dark mode", "Python 3.12").
        source: Where the fact came from ("extracted", "manual", "import").
        confidence: Extraction confidence in [0, 1] (1.0 for manual facts).
        created_at: Unix timestamp of creation.
        tags: Optional free-form tags for filtering.
    """

    subject: str
    predicate: str
    object: str
    source: str = "extracted"
    confidence: float = 1.0
    created_at: float = field(default_factory=time.time)
    tags: list[str] = field(default_factory=list)
    id: str = ""

    def __post_init__(self) -> None:
        if not self.id:
            self.id = _fact_id(self.subject, self.predicate, self.object)


def _fact_id(subject: str, predicate: str, obj: str) -> str:
    """Stable content hash for dedup. Order-independent of tag/input noise."""
    import hashlib

    payload = f"{subject.lower()}|{predicate.lower()}|{obj.lower()}"
    return hashlib.sha1(payload.encode("utf-8")).hexdigest()[:16]


@dataclass
class WikiQueryResult:
    """One hit from a wiki query.

    Attributes:
        fact: The matched Fact.
        score: Relevance score in [0, 1] (1.0 = exact match).
    """

    fact: Fact
    score: float


class WikiBackend(Protocol):
    """Storage backend contract for the wiki.

    The wiki's Markdown source-of-truth is persisted through a backend.
    Local development uses the filesystem; production/server deployment uses
    an HTTP backend (the interface is identical so WikiStore is backend-agnostic).

    Implementations must support:
      - listing/getting/putting/deleting markdown documents
      - exporting all documents (for backup / server sync)
    """

    def list_documents(self) -> list[str]:
        """Return all document names (without extension)."""
        ...

    def get_document(self, name: str) -> str | None:
        """Read a document's Markdown content; None if missing."""
        ...

    def put_document(self, name: str, content: str) -> None:
        """Write (create or overwrite) a document."""
        ...

    def delete_document(self, name: str) -> bool:
        """Delete a document; return True if it existed."""
        ...

    def list_all(self) -> dict[str, str]:
        """Return {name: content} for every document (for export/backup)."""
        ...
