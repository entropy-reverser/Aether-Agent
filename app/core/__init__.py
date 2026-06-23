"""app.core — domain logic (routing, memory, graph, context, progress, tasks).

Each submodule has a single responsibility and exposes a minimal public API
(see the interface contracts in the design plan, §8.2). Heavy dependencies
are imported lazily inside methods so the routing engine stays importable
without the full stack installed.
"""
