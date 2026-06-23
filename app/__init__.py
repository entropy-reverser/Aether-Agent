"""Aether-Agent v2 — a self-evolving digital-human AI companion.

This package implements dynamic model routing, dual-memory, a self-growing
wiki, and cross-window context management. The routing engine (Stage 1) is
the first shippable unit: a zero-LLM, deterministic score-based router.

Design notes
------------
- Version is bumped here on every merge to main (per backward-compat policy).
- Heavy dependencies (chromadb, redis, litellm) are imported lazily inside the
  modules that need them, so importing this top-level package stays cheap.
"""

__version__ = "0.2.0"
__all__ = ["__version__"]
