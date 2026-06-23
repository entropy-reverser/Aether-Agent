# Aether-Agent v2 — Streamlined Implementation Process Plan

> **Purpose**: Experience-transfer document for the next dialogue window. Distills lessons from v1 (2,831 LOC, 36 passing tests, score-based routing engine) into a concrete, constraint-light plan that a more powerful model can execute without re-deriving architecture from scratch.
>
> **Reading time**: ~12 minutes. **Execution time**: 5–7 days for a single capable agent.

---

## 1. Project Requirements

### 1.1 Inherited Functional Requirements (from v1)

A personalized, self-evolving digital-human AI companion with:

- **Dynamic model routing** — three tiers (PARSE/CHAT/COMPLEX) routed by a deterministic score-based engine (zero LLM calls for classification).
- **Dual-memory system** — Redis short-term (last N turns, session-scoped) + Markdown/ChromaDB long-term wiki (global, self-growing).
- **Self-growing wiki** — every N turns, an LLM extracts "permanent facts" into markdown + vector store.
- **Dynamic persona** — system prompt rebuilt each turn from RAG-recalled wiki facts.
- **Enterprise policy engine** — declarative YAML overrides (task_type, project_phase, user_role) + budget guardrails.
- **Adaptive feedback** — user thumbs-up/down adjusts future routing per message signature.

### 1.2 Three New Requirements (v2 focus)

These three requirements are the **primary innovation targets** for v2. They address the real pain point of long-running agentic projects: context decay across windows and uncoordinated parallel work.

#### NEW-1: Single-Window Context Auto-Streamlining

**Problem**: Within a single chat window, after 15–20 turns, the context window fills with stale code, obsolete decisions, and redundant explanations. The model's effective attention degrades even if tokens fit.

**Requirement**: After every N turns (default N=5), automatically produce a compact "context checkpoint" that:
- Summarizes decisions made (not the discussion that led to them).
- Lists the current file inventory with one-line purpose each.
- Captures the last known-good state (what works, what's broken).
- Drops verbatim code blocks older than the checkpoint (they live in files now).
- Preserves the 3 most recent user intents verbatim (for continuity).

**Non-goal**: Do NOT summarize so aggressively that the model loses the ability to reference specific past decisions. The checkpoint must be **lossless for decisions, lossy for prose**.

#### NEW-2: Cross-Window Unified Progress Management

**Problem**: When a task spans multiple chat windows (because one window's context fills up, or the user closes and reopens), there is no standard mechanism to resume. The model re-asks "what are we building?" — destroying continuity.

**Requirement**: A single source-of-truth progress file (`PROGRESS.yaml`) at the project root that:
- Is machine-readable (YAML, not prose) so any window can parse it in one shot.
- Is updated by the agent at the end of every work session (not by the user).
- Contains: current phase, completed subtasks, in-flight subtasks, blocked items, next action, key file paths, environment state.
- Is the **first thing** a new window reads and the **last thing** an old window writes.

**Non-goal**: Do NOT build a complex project-management UI. The file IS the system.

#### NEW-3: Multi-Agent Parallel Processing + Async Finalization

**Problem**: When multiple agents (or multiple subagent invocations) work on different subtasks in parallel, status is scattered across their individual outputs. At project end, async tasks may still be running (tests, builds, extractions) with no graceful finalization.

**Requirement**: A lightweight task ledger (`TASKS.jsonl`) that:
- Records every parallel subtask with: id, owner, status (pending/running/done/failed), started_at, finished_at, artifact_path.
- Supports concurrent writes safely (append-only JSONL).
- On project finalization, the orchestrator scans the ledger, waits for running tasks (with timeout), marks stragglers as `orphaned`, and produces a finalization report.

**Non-goal**: Do NOT build a full distributed task queue (Celery/Temporal). A JSONL file + a finalization script is sufficient for MVP.

---

## 2. Architecture Planning

### 2.1 System Topology

```
┌─────────────────────────────────────────────────────────────┐
│                     Client (REST / WebSocket)                │
└──────────────────────────┬──────────────────────────────────┘
                           │
                           ▼
┌─────────────────────────────────────────────────────────────┐
│  FastAPI (async) — single entry, stateless, horizontally scalable │
│  ├── /api/chat              (REST + WebSocket)               │
│  ├── /api/routing/*         (explain, feedback, reload)      │
│  ├── /api/wiki/*            (query, facts, rebuild)          │
│  ├── /api/progress/*        (NEW-2: read/write PROGRESS.yaml)│
│  ├── /api/tasks/*           (NEW-3: task ledger)             │
│  └── /api/context/*         (NEW-1: checkpoint read/write)   │
└──────────────────────────┬──────────────────────────────────┘
                           │
        ┌──────────────────┼──────────────────┐
        ▼                  ▼                  ▼
┌──────────────┐  ┌──────────────┐  ┌──────────────────┐
│ LangGraph    │  │ Routing      │  │ Memory Layer     │
│ Orchestrator │  │ Engine       │  │ ├ Redis (short)  │
│ (stateful    │  │ (zero-LLM    │  │ ├ Wiki MD+Chroma │
│  graph)      │  │  score-based)│  │ ├ PROGRESS.yaml  │ ← NEW-2
│              │  │              │  │ ├ TASKS.jsonl    │ ← NEW-3
│              │  │              │  │ └ CONTEXT.cp.json│ ← NEW-1
└──────┬───────┘  └──────────────┘  └──────────────────┘
       │
       ▼
┌──────────────────────────────────────────┐
│ LiteLLM (provider-agnostic model caller)  │
│ ├── gpt-4o      (COMPLEX tier)            │
│ ├── gpt-4o-mini (CHAT tier)               │
│ └── llama3:8b   (PARSE tier, local)       │
└──────────────────────────────────────────┘
```

### 2.2 Key Architectural Decisions (with rationale)

| Decision | Rationale |
|---|---|
| **LangGraph for orchestration** | Stateful cyclic graphs; pure-function nodes are testable + replayable. |
| **Deterministic routing (no LLM classifier)** | Saves 100% of classification token cost + ~200ms latency vs LLM-based routing. |
| **Markdown as source of truth, ChromaDB as derived index** | Markdown is human-auditable + git-friendly; ChromaDB can always be rebuilt. |
| **PROGRESS.yaml as cross-window state** | YAML is model-readable in one shot; no DB needed for single-project tracking. |
| **TASKS.jsonl append-only** | Concurrent-safe writes; trivial to tail/grep; no schema migrations. |
| **Lazy heavy imports** | chromadb/redis imported inside methods → unit-testable without full stack. |
| **Stateless FastAPI workers** | All state in Redis/files → horizontal scaling via `replicas: N`. |

### 2.3 What NOT to Build (anti-scope)

To keep the MVP lean, explicitly defer:
- Authentication / multi-tenant isolation (single-user MVP).
- Streaming token responses (add in v2.1).
- Web UI (separate repo).
- Distributed task queue (Celery/Temporal) — JSONL suffices.
- Custom embedding model fine-tuning.

---

## 3. Stage-by-Stage Task Breakdown

Each stage is **independently shippable** and ends with a green test suite + a git commit. Stages are ordered by dependency, not by calendar day — a capable agent may compress multiple stages into one session.

### Stage 0 — Foundation (prerequisite, ~2 hours)

**Single task**: Scaffold project skeleton + CI skeleton.

- [ ] Create directory structure (see §5.1).
- [ ] Write `requirements.txt` with pinned versions.
- [ ] Write `.env.example` with all config keys.
- [ ] Write `pyproject.toml` with ruff + mypy config.
- [ ] Write `.github/workflows/ci.yml` (lint + test on push).
- [ ] Write `Dockerfile` + `docker-compose.yml`.
- [ ] Initial commit: `chore: scaffold project skeleton`.

**Exit criteria**: `docker compose up` starts Redis + app; `curl /api/health` returns 200.

### Stage 1 — Routing Engine (core IP, ~1 day)

**Single task**: Implement the zero-LLM score-based routing engine.

- [ ] `app/core/routing/tiers.py` — Tier enum + model mapping.
- [ ] `app/core/routing/signals.py` — 7 deterministic signal extractors.
- [ ] `app/core/routing/scorer.py` — combine signals → 0-100 score.
- [ ] `app/core/routing/policy.py` — YAML-driven enterprise overrides + budget guardrails.
- [ ] `app/core/routing/feedback.py` — adaptive feedback store.
- [ ] `app/core/routing/router.py` — RoutingEngine orchestrator.
- [ ] `tests/test_routing.py` — ≥30 tests covering signals, scorer, policy, feedback, end-to-end.
- [ ] `enterprise_routing.example.yaml` — documented example policy.

**Exit criteria**: `pytest tests/test_routing.py` green; `POST /api/routing/explain` returns full breakdown in <5ms.

### Stage 2 — Memory Layer (dual-memory, ~1 day)

**Single task**: Implement short-term Redis memory + long-term wiki.

- [ ] `app/core/memory.py` — Redis-backed session memory (sliding window + TTL).
- [ ] `app/core/wiki.py` — Markdown + ChromaDB long-term store + LLM extractor.
- [ ] `app/core/persona.py` — dynamic system prompt from RAG-recalled facts.
- [ ] `tests/test_memory.py` — session lifecycle, turn append/trim, wiki fact dedup.

**Exit criteria**: Can append 15 turns, verify only last 10 retained; can extract a fact and query it back via RAG.

### Stage 3 — LangGraph Orchestration (~0.5 day)

**Single task**: Wire the graph: classify → build_prompt → respond → persist → maybe_extract.

- [ ] `app/core/graph.py` — 5 nodes + edges + state schema.
- [ ] `app/core/router.py` (rename to `model_caller.py`) — LiteLLM wrapper with retry + fallback.
- [ ] `tests/test_graph.py` — graph compiles, state schema correct, node contracts.

**Exit criteria**: `aether_graph.ainvoke(state)` returns a complete response with routing decision attached.

### Stage 4 — NEW-1: Context Auto-Streamlining (~1 day)

**Single task**: Implement the context checkpoint system.

- [ ] `app/core/context.py` — `ContextCheckpoint` dataclass + `streamline()` function.
- [ ] Trigger: after every N turns (configurable), produce a checkpoint.
- [ ] `app/api/routes.py` — `GET /api/context/{session_id}` + `POST /api/context/streamline`.
- [ ] `tests/test_context.py` — checkpoint is lossless for decisions, lossy for prose.

**Exit criteria**: A 20-turn conversation produces a <2KB checkpoint that preserves all decisions + last 3 intents.

### Stage 5 — NEW-2: Cross-Window Progress Management (~0.5 day)

**Single task**: Implement `PROGRESS.yaml` read/write + session resume protocol.

- [ ] `app/core/progress.py` — `ProgressTracker` class (load/save/patch).
- [ ] `PROGRESS.yaml` at project root — single source of truth.
- [ ] `app/api/routes.py` — `GET /api/progress` + `POST /api/progress/update`.
- [ ] `scripts/resume.py` — CLI that reads PROGRESS.yaml and prints "next action" for a new window.
- [ ] `tests/test_progress.py` — round-trip save/load, concurrent-safe patch.

**Exit criteria**: Window A writes progress; Window B reads it and knows exactly what to do next without asking.

### Stage 6 — NEW-3: Multi-Agent Task Ledger (~0.5 day)

**Single task**: Implement `TASKS.jsonl` + finalization script.

- [ ] `app/core/tasks.py` — `TaskLedger` class (append, list, finalize).
- [ ] `app/api/routes.py` — `POST /api/tasks` (create), `PATCH /api/tasks/{id}` (update), `GET /api/tasks` (list).
- [ ] `scripts/finalize.py` — scans ledger, waits for running tasks (timeout 60s), marks orphans, emits report.
- [ ] `tests/test_tasks.py` — concurrent append safety, finalization correctness.

**Exit criteria**: 5 parallel subtasks write to ledger; `finalize.py` produces a clean report with no orphans.

### Stage 7 — API Polish + Docs (~0.5 day)

**Single task**: API design review + documentation.

- [ ] Audit all endpoints for RESTful consistency (see §7).
- [ ] Add OpenAPI tags + examples in `app/api/schemas.py`.
- [ ] Write `README.md` with Mermaid architecture diagram + quickstart.
- [ ] Write `docs/API.md` with curl examples for every endpoint.
- [ ] Write `docs/DEPLOYMENT.md` (Docker + cloud + GitHub Actions).

**Exit criteria**: `README.md` quickstart works copy-paste; all endpoints documented with examples.

### Stage 8 — CI/CD + Deployment (~0.5 day)

**Single task**: Wire CI/CD pipeline + cloud deployment artifacts.

- [ ] `.github/workflows/ci.yml` — lint (ruff) + type-check (mypy) + test (pytest) on every push.
- [ ] `.github/workflows/deploy.yml` — build Docker image on tag, push to GHCR.
- [ ] `deploy/cloud-init.yaml` — one-command cloud server bootstrap.
- [ ] `Makefile` — `make test`, `make lint`, `make run`, `make deploy`.

**Exit criteria**: Push to `main` → CI green → image published to GHCR → cloud server pulls + restarts.

---

## 4. Development Environment

### 4.1 Required Tools

| Tool | Version | Purpose |
|---|---|---|
| Python | 3.11+ | Runtime |
| Docker + Compose | 24+ / v2 | Local stack + deployment |
| Git | 2.40+ | Version control |
| ruff | 0.6+ | Linter + formatter (replaces black + isort + flake8) |
| mypy | 1.11+ | Static type checking |
| pytest | 8+ | Test runner |
| uvicorn | 0.30+ | ASGI server |
| Redis | 7+ | Short-term memory |
| ChromaDB | 0.5+ | Vector store |
| Ollama (optional) | 0.3+ | Local Llama-3-8B for PARSE tier |

### 4.2 Recommended Editor Setup

- **VS Code / Cursor** with extensions: Python, Ruff, Docker, YAML, Markdown All-in-One.
- **Settings**: format-on-save (ruff), type-check on save (mypy), test discovery on `tests/`.
- **AI assistance**: Cursor's Composer for multi-file edits; GitHub Copilot for inline completion.

### 4.3 Environment Variables (`.env`)

Single file, gitignored. See `.env.example` for the full template. Key categories:
- LLM provider keys (`OPENAI_API_KEY`, optional `LOCAL_LLM_API_BASE`).
- Model tier mapping (`ROUTER_MODEL_COMPLEX/CHAT/PARSE`).
- Routing thresholds (`ROUTING_PARSE_MAX=25`, `ROUTING_CHAT_MAX=55`).
- Storage paths (`REDIS_URL`, `CHROMA_PERSIST_DIR`, `WIKI_DIR`).
- New v2 paths (`PROGRESS_FILE=PROGRESS.yaml`, `TASKS_FILE=TASKS.jsonl`, `CONTEXT_DIR=./data/context`).

---

## 5. Tech Stack Specifications

### 5.1 Directory Structure (canonical)

```
aether-agent/
├── app/
│   ├── __init__.py
│   ├── main.py                    # FastAPI entry + lifespan
│   ├── config.py                  # Pydantic settings (single source of truth)
│   ├── api/
│   │   ├── __init__.py
│   │   ├── routes.py              # All endpoints (thin controllers)
│   │   └── schemas.py             # Pydantic request/response models
│   ├── core/
│   │   ├── __init__.py
│   │   ├── graph.py               # LangGraph orchestration
│   │   ├── model_caller.py        # LiteLLM wrapper (renamed from router.py)
│   │   ├── memory.py              # Redis short-term
│   │   ├── wiki.py                # Markdown + ChromaDB long-term
│   │   ├── persona.py             # Dynamic system prompt
│   │   ├── context.py             # NEW-1: context checkpoint
│   │   ├── progress.py            # NEW-2: PROGRESS.yaml tracker
│   │   ├── tasks.py               # NEW-3: TASKS.jsonl ledger
│   │   └── routing/
│   │       ├── __init__.py
│   │       ├── tiers.py
│   │       ├── signals.py
│   │       ├── scorer.py
│   │       ├── policy.py
│   │       ├── feedback.py
│   │       └── router.py
│   └── utils/
│       ├── __init__.py
│       └── logger.py              # loguru structured logging
├── tests/
│   ├── test_routing.py
│   ├── test_memory.py
│   ├── test_graph.py
│   ├── test_context.py
│   ├── test_progress.py
│   └── test_tasks.py
├── scripts/
│   ├── init_db.py
│   ├── resume.py                  # NEW-2: cross-window resume CLI
│   └── finalize.py                # NEW-3: project finalization
├── wiki/                           # Long-term markdown memory
├── data/                           # ChromaDB + context checkpoints
├── docs/
│   ├── API.md
│   └── DEPLOYMENT.md
├── .github/workflows/
│   ├── ci.yml
│   └── deploy.yml
├── PROGRESS.yaml                   # NEW-2: cross-window state
├── TASKS.jsonl                     # NEW-3: task ledger
├── enterprise_routing.example.yaml
├── Dockerfile
├── docker-compose.yml
├── requirements.txt
├── pyproject.toml                  # ruff + mypy config
├── Makefile
├── .env.example
└── README.md
```

### 5.2 Dependency Pinning Rules

- **Pin major.minor** in `requirements.txt` (e.g., `fastapi==0.115.0`).
- **Allow patch upgrades** only via Dependabot (configured in `.github/dependabot.yml`).
- **Separate dev deps** into `requirements-dev.txt` (pytest, mypy, ruff).
- **No transitive deps** in requirements — only direct imports.

---

## 6. Development Tools Best Practices

### 6.1 Code Style (enforced by ruff)

- Line length: 100 chars.
- Import sorting: stdlib → third-party → local (ruff handles this).
- Docstrings: Google style for all public functions/classes.
- Type hints: mandatory on all public APIs; optional on private helpers.
- No `print()` — use `loguru` exclusively.

### 6.2 Git Workflow

- **Branch per stage**: `stage-1-routing`, `stage-2-memory`, etc.
- **Commit message format**: `<type>(<scope>): <subject>` (Conventional Commits).
  - Types: `feat`, `fix`, `test`, `docs`, `refactor`, `chore`, `ci`.
  - Example: `feat(routing): add budget guardrail to policy engine`.
- **PR per stage** → squash-merge to `main` after CI green.
- **Never commit** `.env`, `data/`, `logs/`, `__pycache__/`.

### 6.3 Testing Discipline

- **Test pyramid**: 70% unit (signals, scorer), 20% integration (graph nodes), 10% e2e (API endpoints).
- **Test names**: `test_<unit>_<scenario>_<expectation>` (e.g., `test_scorer_coding_question_scores_high`).
- **No network in unit tests** — mock LiteLLM / Redis / ChromaDB.
- **Coverage target**: ≥80% for `app/core/`, ≥60% overall (enforced in CI).

---

## 7. API Design Best Practices

### 7.1 RESTful Conventions

- **Resource-oriented URLs**: `/api/sessions`, `/api/wiki/facts`, `/api/tasks/{id}`.
- **HTTP methods**: GET (read, idempotent), POST (create), PATCH (partial update), DELETE (remove).
- **Status codes**: 200 (ok), 201 (created), 400 (bad request), 404 (not found), 422 (validation error), 500 (server error).
- **Pagination**: `?limit=20&offset=0` for list endpoints; response includes `total`.
- **Filtering**: `?status=running&owner=agent-3` as query params.

### 7.2 Response Envelope

All responses use a consistent envelope:

```json
{
  "data": { ... },           // the actual payload
  "meta": {                  // optional metadata
    "request_id": "uuid",
    "latency_ms": 12.3
  },
  "error": null              // null on success, {code, message} on failure
}
```

### 7.3 Error Handling

- Never leak stack traces to clients (log them server-side via loguru).
- Error codes are stable strings: `ROUTING_POLICY_INVALID`, `WIKI_CORRUPT`, `TASK_NOT_FOUND`.
- Validation errors (422) include field-level details from Pydantic.

### 7.4 Versioning

- URL versioning: `/api/v1/...` (reserve for breaking changes).
- Additive changes (new fields, new endpoints) do NOT require version bump.
- Document deprecations in `docs/API.md` with sunset date.

### 7.5 WebSocket Conventions

- URL: `/api/ws/chat`.
- Message format: `{"type": "intent|message|error|facts", "payload": {...}}`.
- Server sends `{"type": "ping"}` every 30s; client must respond `{"type": "pong"}` within 10s.

---

## 8. Modular Functionality Design

### 8.1 Module Independence Rules

Every module in `app/core/` must satisfy:

1. **Single responsibility** — one module, one concern (e.g., `memory.py` only handles Redis, nothing else).
2. **No circular imports** — `routing/` never imports `graph.py`; `graph.py` imports `routing/`.
3. **Lazy heavy deps** — `chromadb`, `redis`, `litellm` imported inside methods, not at module top.
4. **Pure functions where possible** — signal extractors, scorer, policy matcher are pure.
5. **Singletons at module bottom** — `wiki_store = WikiStore()`, `routing_engine = RoutingEngine()`.

### 8.2 Interface Contracts

Each module exposes a minimal public API (everything else is private `_`):

| Module | Public API |
|---|---|
| `routing/` | `RoutingEngine.route(msg, ctx) -> RoutingDecision` |
| `memory.py` | `ShortTermMemory.{connect, append_turn, get_turns, clear_session}` |
| `wiki.py` | `WikiStore.{init, add_fact, query, extract_from_turns, rebuild_from_markdown}` |
| `persona.py` | `PersonaBuilder.build(user_message, user_id) -> str` |
| `context.py` | `ContextCheckpoint.{create, load, save, streamline}` |
| `progress.py` | `ProgressTracker.{load, save, patch, next_action}` |
| `tasks.py` | `TaskLedger.{create, update, list, finalize}` |

---

## 9. Code Simplification Principles

### 9.1 Anti-bloat Rules

- **No function > 40 lines** — if longer, extract a helper.
- **No file > 200 lines** — if longer, split by concern.
- **No class > 5 public methods** — if more, split the class.
- **No nested ifs > 3 levels** — flatten with early returns or extract.
- **No comments explaining WHAT** — only WHY. The code shows what; comments show why.

### 9.2 Delete Code Ruthlessly

- Dead code = liability. If a function isn't called, delete it (git remembers).
- Commented-out code = forbidden. Use git history, not comments.
- "Just in case" parameters = forbidden. Add them when needed (YAGNI).

### 9.3 Prefer Composition Over Inheritance

- No class hierarchies deeper than 2 levels.
- Use dataclasses + protocols, not abstract base classes.
- Inject dependencies via constructor, not globals (except documented singletons).

---

## 10. Documentation & Comment Standards

### 10.1 Module-Level Docstring (mandatory)

Every `.py` file starts with:

```python
"""<Module name> — <one-line summary>.

<2-4 sentences explaining: what this module does, why it exists,
and how it fits into the larger system. Mention key design decisions
and trade-offs.>

Design notes
------------
- <decision 1 + rationale>
- <decision 2 + rationale>
"""
```

### 10.2 Function/Class Docstring (mandatory for public API)

Google style:

```python
def route(self, message: str, ctx: RoutingContext) -> RoutingDecision:
    """Route a message to the appropriate model tier.

    Uses a deterministic 4-stage pipeline (signals → scorer → feedback → policy)
    with zero LLM calls. Total latency: <5ms for any message.

    Args:
        message: The user's input message (1-8000 chars).
        ctx: Enterprise routing context (user_role, task_type, etc.).

    Returns:
        A RoutingDecision with tier, model, score breakdown, and audit reasons.

    Raises:
        ValueError: If message is empty.
    """
```

### 10.3 Inline Comments (sparingly)

- Only for non-obvious WHY (never WHAT).
- Format: `# WHY: <explanation>` to distinguish from commented-out code.
- Example: `# WHY: cosine similarity > 0.92 means semantic duplicate (empirically tuned)`

### 10.4 README Structure

1. One-paragraph elevator pitch.
2. Architecture diagram (Mermaid).
3. Quickstart (3 commands max).
4. API reference table.
5. Configuration guide.
6. Deployment guide.
7. Roadmap.

---

## 11. Iteration & Extensibility

### 11.1 Extension Points (designed-in)

| Want to extend... | How |
|---|---|
| Add a 4th routing tier | Add `Tier.ULTRA` in `tiers.py` + threshold in `scorer.py` |
| Add a new signal | Write `xxx_signal()` in `signals.py`, append to `SIGNALS` list |
| Add a new memory backend | Implement `ShortTermMemory` interface with Postgres/SQLite |
| Add a new wiki source | Add a loader in `wiki.py` that ingests from URL/DB → markdown |
| Add a new graph node | Write async function, `g.add_node(...)`, wire edges |
| Add enterprise policy rule | Edit `enterprise_routing.yaml`, call `POST /api/routing/reload` |

### 11.2 Backward Compatibility Rules

- Never remove a public API — deprecate for one release, then remove.
- Never change a response field type — add a new field instead.
- Never change a config key name — alias the old name.
- Bump version in `app/__init__.py` on every merge to `main`.

### 11.3 Feature Flags

For risky/experimental features, gate behind env flags:

```python
if settings.enable_streaming:  # default False in v2, True in v2.1
    return await _stream_response(...)
return await _batch_response(...)
```

---

## 12. Performance & Observability

### 12.1 Performance Targets

| Metric | Target |
|---|---|
| Routing decision latency | <5ms (zero LLM) |
| Chat response (CHAT tier) | <2s p95 |
| Chat response (COMPLEX tier) | <8s p95 |
| Wiki RAG query | <50ms p95 |
| Memory append (Redis) | <2ms p95 |
| Context checkpoint creation | <500ms |

### 12.2 Logging (loguru)

- **Levels**: DEBUG (dev), INFO (prod default), WARNING (degraded), ERROR (failed).
- **Structured fields**: every log includes `request_id`, `user_id`, `session_id`, `latency_ms`.
- **Rotation**: 10MB per file, retain 7 days, compress to zip.
- **Never log**: API keys, full user messages (truncate to 60 chars), PII.

### 12.3 Metrics (Prometheus-ready, deferred to v2.1)

Expose `/metrics` endpoint with:
- `aether_routing_decisions_total{tier=...}` counter.
- `aether_llm_latency_seconds{model=...}` histogram.
- `aether_wiki_facts_count` gauge.
- `aether_active_sessions` gauge.

### 12.4 Health Checks

`GET /api/health` returns:
```json
{
  "status": "ok|degraded|down",
  "redis": "ok|error: <msg>",
  "chroma": "ok|not_initialized",
  "wiki_facts": 42,
  "uptime_seconds": 3600
}
```

---

## 13. Self-Validation

### 13.1 Pre-Commit Checklist (agent runs before every commit)

- [ ] `ruff check app/ tests/` — zero errors.
- [ ] `ruff format --check app/ tests/` — zero diffs.
- [ ] `mypy app/` — zero errors (warnings OK).
- [ ] `pytest tests/ -v` — all green.
- [ ] No `# TODO` without a linked issue.
- [ ] No `print()` statements (use loguru).
- [ ] No commented-out code.

### 13.2 Stage-Exit Validation

At the end of each stage (§3), the agent must verify:

- [ ] All tests for this stage pass.
- [ ] No regressions in prior stage tests.
- [ ] `PROGRESS.yaml` updated with stage completion.
- [ ] Git commit made with Conventional Commit message.
- [ ] README updated if user-facing behavior changed.

### 13.3 Project-End Validation (Stage 8+)

- [ ] `docker compose up` works from clean clone.
- [ ] All endpoints respond correctly (run `scripts/smoke_test.sh`).
- [ ] `PROGRESS.yaml` shows 100% stage completion.
- [ ] `TASKS.jsonl` has no orphaned tasks.
- [ ] `docs/API.md` matches actual API.
- [ ] CI pipeline green on `main`.

---

## 14. CI/CD Best Practices

### 14.1 CI Pipeline (`.github/workflows/ci.yml`)

Triggers on every push + PR. Jobs:

1. **lint** — `ruff check` + `ruff format --check` (30s).
2. **typecheck** — `mypy app/` (60s).
3. **test** — `pytest tests/ --cov=app --cov-fail-under=80` (120s).
4. **build** — `docker build .` (180s, only on main + tags).

Matrix: Python 3.11 + 3.12. Fail fast on lint; run test on both versions in parallel.

### 14.2 CD Pipeline (`.github/workflows/deploy.yml`)

Triggers on tag `v*.*.*`. Jobs:

1. **build-image** — build Docker image, push to `ghcr.io/<org>/aether-agent:<tag>`.
2. **deploy-staging** — SSH to staging server, `docker compose pull && docker compose up -d`.
3. **smoke-test** — curl staging `/api/health` until green (retry 5×).
4. **deploy-prod** — manual approval gate, then same as staging.

### 14.3 Branch Protection Rules

- `main`: require PR review, require CI green, no force-push.
- `develop`: require CI green, allow force-push (for rebasing).
- Feature branches: auto-delete on merge.

### 14.4 Release Process

1. Update `app/__init__.py` version.
2. Update `CHANGELOG.md` (Keep a Changelog format).
3. Tag: `git tag v0.2.0 && git push --tags`.
4. CD pipeline handles the rest.

---

## 15. Deployment Integration

### 15.1 Docker (local + production)

- **Dockerfile**: multi-stage (builder + runtime), final image <300MB.
- **docker-compose.yml**: Redis + app + (optional) Ollama for local Llama.
- **Volumes**: `data/` (ChromaDB), `wiki/` (markdown), `logs/`.
- **Healthcheck**: `curl -f http://localhost:8000/api/health || exit 1`.

### 15.2 GitHub (CI/CD + registry)

- **GHCR**: container registry at `ghcr.io/<org>/aether-agent`.
- **GitHub Actions**: CI + CD pipelines (see §14).
- **Dependabot**: weekly PRs for dependency bumps.
- **GitHub Pages**: auto-publish `docs/` as a static site (optional).

### 15.3 Cloud Server (one-command bootstrap)

`deploy/cloud-init.yaml` provisions a fresh Ubuntu 22.04 VM:

1. Install Docker + docker-compose.
2. Create `aether` user.
3. Clone repo to `/opt/aether-agent`.
4. Copy `.env` from secrets manager (or prompt user).
5. `docker compose up -d`.
6. Configure nginx reverse proxy + Let's Encrypt (optional).

Usage:
```bash
# On a fresh cloud VM:
wget https://raw.githubusercontent.com/<org>/aether-agent/main/deploy/cloud-init.yaml
sudo cloud-init init --file cloud-init.yaml
```

### 15.4 Makefile (developer ergonomics)

```makefile
.PHONY: install test lint typecheck run deploy clean

install:
	pip install -r requirements.txt -r requirements-dev.txt

test:
	pytest tests/ -v --cov=app

lint:
	ruff check app/ tests/
	ruff format --check app/ tests/

typecheck:
	mypy app/

run:
	uvicorn app.main:app --reload --host 0.0.0.0 --port 8000

deploy:
	docker compose build && docker compose up -d

clean:
	find . -type d -name __pycache__ -exec rm -rf {} +
	rm -rf .pytest_cache data/ logs/
```

---

## 16. Constraint-Light Design Philosophy

This plan deliberately avoids over-constraining the implementing model. Specifically:

- **No fixed hourly estimates** — stages take as long as they take; the agent self-paces.
- **No mandatory tooling lock-in** — if the agent prefers `poetry` over `pip`, that's fine as long as `requirements.txt` stays in sync.
- **No rigid file naming** — the structure in §5.1 is canonical but not mandatory; the agent may refactor if it improves clarity.
- **No prohibition on AI assistance** — the agent may use any tool (Cursor, Copilot, etc.) to accelerate.
- **No requirement to follow this plan linearly** — if the agent discovers a better order, it should document the deviation in `PROGRESS.yaml` and proceed.

The only hard constraints are:
1. Every stage ends with green tests + a git commit.
2. `PROGRESS.yaml` is the single source of truth for cross-window continuity.
3. No secrets in code.
4. No artificial ending markers in generated files.

---

## Appendix A: Quick Reference — New v2 Files

| File | Purpose | Created in Stage |
|---|---|---|
| `app/core/context.py` | NEW-1: context checkpoint | Stage 4 |
| `app/core/progress.py` | NEW-2: PROGRESS.yaml tracker | Stage 5 |
| `app/core/tasks.py` | NEW-3: TASKS.jsonl ledger | Stage 6 |
| `PROGRESS.yaml` | Cross-window state (project root) | Stage 5 |
| `TASKS.jsonl` | Task ledger (project root) | Stage 6 |
| `scripts/resume.py` | Cross-window resume CLI | Stage 5 |
| `scripts/finalize.py` | Project finalization script | Stage 6 |
| `data/context/` | Stored context checkpoints | Stage 4 |

## Appendix B: Stage Dependency Graph

```
Stage 0 (Foundation)
   │
   ▼
Stage 1 (Routing) ──────────┐
   │                         │
   ▼                         ▼
Stage 2 (Memory)      Stage 4 (Context) ← NEW-1
   │                         │
   ▼                         │
Stage 3 (Graph) ◄────────────┘
   │
   ├──► Stage 5 (Progress) ← NEW-2
   │
   ├──► Stage 6 (Tasks) ← NEW-3
   │
   ▼
Stage 7 (API + Docs)
   │
   ▼
Stage 8 (CI/CD + Deploy)
```

Stages 4, 5, 6 can be done in parallel after Stage 3 (they have no inter-dependencies).
