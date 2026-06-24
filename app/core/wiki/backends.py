"""app.core.wiki.backends — storage backend implementations.

Two backends share the ``WikiBackend`` protocol (models.py):
  - ``LocalFilesystemBackend``: Markdown files on disk. Default for dev/tests.
  - ``HttpBackend``: talks to a remote wiki server over REST. For server
    deployment (the interface is reserved here; full impl lands with Stage 8).

Design notes
------------
- Both backends are constructed with plain config (paths / URLs) so WikiStore
  can swap them without touching business logic.
- The HTTP backend uses lazy-imported ``requests`` so the wiki module stays
  importable without it. For MVP the HTTP backend raises ``NotImplementedError``
  on writes but documents the exact REST contract a server must implement.
"""

from __future__ import annotations

from pathlib import Path

from app.utils.logger import logger


class LocalFilesystemBackend:
    """Filesystem-backed wiki storage. One Markdown file per document.

    Args:
        root: Directory holding the markdown files (e.g. ./wiki).
    """

    def __init__(self, root: str | Path) -> None:
        self.root = Path(root)
        self.root.mkdir(parents=True, exist_ok=True)

    def _path(self, name: str) -> Path:
        return self.root / f"{name}.md"

    def list_documents(self) -> list[str]:
        return sorted(p.stem for p in self.root.glob("*.md"))

    def get_document(self, name: str) -> str | None:
        path = self._path(name)
        if not path.exists():
            return None
        return path.read_text(encoding="utf-8")

    def put_document(self, name: str, content: str) -> None:
        self._path(name).write_text(content, encoding="utf-8")

    def delete_document(self, name: str) -> bool:
        path = self._path(name)
        if path.exists():
            path.unlink()
            return True
        return False

    def list_all(self) -> dict[str, str]:
        return {
            name: content
            for name in self.list_documents()
            if (content := self.get_document(name)) is not None
        }


class HttpBackend:
    """REST-based wiki backend for server deployment.

    Talks to a remote wiki server. The REST contract a server must implement:

        GET    /api/wiki/documents            -> ["user", "project", ...]
        GET    /api/wiki/documents/{name}     -> "# user\\n\\n- prefers ..."
        PUT    /api/wiki/documents/{name}     -> 204 (body: markdown content)
        DELETE /api/wiki/documents/{name}     -> 204
        GET    /api/wiki/export               -> {name: content, ...}

    Args:
        base_url: Server root, e.g. "https://wiki.example.com".
        api_key: Optional bearer token for authenticated deployments.

    Note:
        For MVP this backend is a documented stub: reads work against any
        compliant server (once ``requests`` is installed), writes raise
        NotImplementedError until Stage 8 wires the server. This keeps the
        deploy interface fixed now so WikiStore code never changes later.
    """

    def __init__(self, base_url: str, api_key: str | None = None) -> None:
        self.base_url = base_url.rstrip("/")
        self.api_key = api_key

    def _headers(self) -> dict[str, str]:
        h = {"Content-Type": "text/markdown; charset=utf-8"}
        if self.api_key:
            h["Authorization"] = f"Bearer {self.api_key}"
        return h

    def _get(self, path: str) -> str:
        try:
            import requests  # lazy import
        except ImportError as exc:  # pragma: no cover
            raise RuntimeError("install 'requests' to use the HTTP wiki backend") from exc
        resp = requests.get(f"{self.base_url}{path}", headers=self._headers(), timeout=10)
        resp.raise_for_status()
        return resp.text

    def list_documents(self) -> list[str]:
        try:
            import requests
        except ImportError as exc:  # pragma: no cover
            raise RuntimeError("install 'requests' to use the HTTP wiki backend") from exc
        resp = requests.get(f"{self.base_url}/api/wiki/documents", headers=self._headers(), timeout=10)
        resp.raise_for_status()
        return list(resp.json())

    def get_document(self, name: str) -> str | None:
        try:
            return self._get(f"/api/wiki/documents/{name}")
        except Exception as exc:  # noqa: BLE001
            logger.debug("HttpBackend get_document miss for {}: {}", name, exc)
            return None

    def put_document(self, name: str, content: str) -> None:
        # WHY: reserved interface; full server write path lands at Stage 8.
        raise NotImplementedError(
            "HttpBackend writes are reserved for server deployment (Stage 8). "
            "REST contract: PUT /api/wiki/documents/{name}"
        )

    def delete_document(self, name: str) -> bool:
        raise NotImplementedError(
            "HttpBackend deletes are reserved for server deployment (Stage 8)."
        )

    def list_all(self) -> dict[str, str]:
        try:
            import requests
        except ImportError as exc:  # pragma: no cover
            raise RuntimeError("install 'requests' to use the HTTP wiki backend") from exc
        resp = requests.get(f"{self.base_url}/api/wiki/export", headers=self._headers(), timeout=10)
        resp.raise_for_status()
        return dict(resp.json())
