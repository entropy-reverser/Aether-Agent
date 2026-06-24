"""app.core.wiki — self-growing long-term memory.

Markdown is the source of truth; the vector index is a derived, rebuildable
artifact. The store is backend-agnostic: local filesystem for dev/tests, an
HTTP backend for server deployment (interface reserved).

Public API
----------
- ``Fact``: the unit of long-term memory (content-hash deduplicated).
- ``WikiStore``: add/query/export facts; serializes to Markdown per subject.
- ``WikiBackend``: storage protocol; ``LocalFilesystemBackend`` + ``HttpBackend``.
- ``extract_from_turns``: deterministic rule-based fact extractor.
- ``wiki_store``: process-wide singleton backed by ``settings.wiki_dir``.
"""

from __future__ import annotations

from app.core.wiki.backends import HttpBackend, LocalFilesystemBackend
from app.core.wiki.extractor import extract_from_turns
from app.core.wiki.models import Fact, WikiBackend, WikiQueryResult
from app.core.wiki.store import WikiStore
from app.utils.logger import logger

__all__ = [
    "Fact",
    "HttpBackend",
    "LocalFilesystemBackend",
    "WikiBackend",
    "WikiQueryResult",
    "WikiStore",
    "extract_from_turns",
    "get_wiki_store",
    "wiki_store",
]


def _build_wiki_store() -> WikiStore:
    """Construct the singleton store from ``settings.wiki_dir``."""
    from app.config import settings  # lazy: avoids import cycle at package load

    backend = LocalFilesystemBackend(settings.wiki_dir)
    store = WikiStore(backend)
    try:
        store.init()
    except Exception as exc:  # pragma: no cover - init is best-effort at import
        logger.warning("wiki store init deferred: {}", exc)
    return store


def get_wiki_store() -> WikiStore:
    """Return the process-wide wiki store (creates it on first call)."""
    global wiki_store
    if wiki_store is None:
        wiki_store = _build_wiki_store()
    return wiki_store


# Lazy singleton: None until first access via get_wiki_store().
# WHY: importing the package must stay side-effect free for tests; the store
# is only built when something actually needs it.
wiki_store: WikiStore | None = None
