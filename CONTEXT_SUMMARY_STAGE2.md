# Context Summary — Stage 2 Wiki MVP Complete

> Generated: 2026-06-24 · Authoritative handoff for the next window.
> Follows `Aether_Agent_v2_Context_Management_Rules.md` §4.3 (Resume Brief).

---

## [Resume Brief]

```
Project: aether-agent-v2 (v0.2.0)
Stage:   stage-2-memory (wiki MVP complete) — next: Stage 3 (LangGraph) or dual-memory
Overall: ~33% (Stage 0 + Stage 1 routing + Stage 2 wiki MVP done)
Last work: Self-growing wiki store, 53 new tests (126 total), 92% coverage, commit 23b65e1
Next action: Either (A) LangGraph agent graph + LLMFactExtractor, (B) dual-memory session
             layer bridging routing->wiki, or (C) ChromaDB vector-indexed semantic query
Blockers: none (HttpBackend writes + ChromaDB + LLM extractor are reserved stubs by design)
```

---

## 1. What Was Built This Stage

Self-growing long-term memory (wiki) — the foundation for all persistent memory.

**Pipeline:**
```
conversation turns
  → [extractor] deterministic bilingual regex → Facts (confidence-tagged)
  → [store]     add_fact (content-hash dedup) → per-subject Markdown document
  → [query]     substring (1.0) + Jaccard token overlap (0..1) → ranked results
  → [REST]      /api/wiki/{facts,query,extract,rebuild,export}
```

**Key design choices:**
- **Markdown is source of truth.** Vector index is a derived, rebuildable artifact (never the other way). Human-auditable, git-friendly, survives vector-store corruption.
- **Pluggable `WikiBackend` Protocol.** `LocalFilesystemBackend` (working) + `HttpBackend` (REST stub for server deploy). WikiStore code never changes when the server lands.
- **Content-hash dedup.** Fact.id = SHA1[:16] of `subject|predicate|object` (case-folded). Re-extracting the same fact is a no-op.
- **Deterministic extractor first.** 7 bilingual regex patterns (name/prefer/use/remember/project). LLM hook (`LLMFactExtractor`) raises NotImplementedError — reserved for Stage 3. Tests run network-free.
- **Lossless Markdown round-trip.** `_render_markdown` ↔ `_parse_markdown` preserve fact identity (content hash collides).

---

## 2. Project Structure (current)

```
aether-agent/                      (branch stage-1-routing, commit 23b65e1)
├── app/
│   ├── api/
│   │   ├── routes.py              # routing endpoints (unchanged)
│   │   ├── wiki_routes.py         # NEW: /api/wiki/* endpoints
│   │   └── schemas.py             # + FactIn/FactOut/WikiQueryHit/ExtractRequest
│   ├── core/
│   │   ├── routing/               # unchanged (Stage 1)
│   │   └── wiki/                  # NEW
│   │       ├── __init__.py        # public API + lazy get_wiki_store() singleton
│   │       ├── models.py          # Fact (content-hash) + WikiBackend Protocol + WikiQueryResult
│   │       ├── backends.py        # LocalFilesystemBackend + HttpBackend (REST stub)
│   │       ├── extractor.py       # extract_from_turns (regex) + LLMFactExtractor stub
│   │       └── store.py           # WikiStore: init/add/query/list/rebuild/export
│   ├── main.py                    # + wiki_router mount
│   └── config.py                  # wiki_dir setting (./wiki default)
├── tests/
│   ├── test_wiki.py               # NEW: 40 tests (model, round-trip, store, query, backend, extractor)
│   └── test_wiki_api.py           # NEW: 13 tests (REST endpoints, temp-dir store)
├── data/context/stage-2.cp.json   # NEW: ContextCheckpoint
├── PROGRESS.yaml                  # updated: stage-2 wiki subtasks done, 126 tests, 92%
└── CONTEXT_SUMMARY_STAGE2.md      # this file
```

---

## 3. REST API (wiki)

| Method | Path | Purpose |
|---|---|---|
| GET | `/api/wiki/facts?subject=` | List facts, optional subject filter |
| POST | `/api/wiki/facts` | Add one manual fact (source=manual, confidence=1.0) |
| GET | `/api/wiki/query?q=&limit=` | Natural-language query, ranked hits |
| POST | `/api/wiki/extract` | Extract+store facts from conversation turns |
| POST | `/api/wiki/rebuild` | Reload in-memory index from Markdown |
| GET | `/api/wiki/export` | Dump all documents as {name: markdown} |

**HttpBackend REST contract (for server deploy, Stage 8):**
```
GET    /api/wiki/documents            -> ["user", "project", ...]
GET    /api/wiki/documents/{name}     -> markdown content
PUT    /api/wiki/documents/{name}     -> 204 (body: markdown)
DELETE /api/wiki/documents/{name}     -> 204
GET    /api/wiki/export               -> {name: content, ...}
```

---

## 4. Implemented vs Reserved

### ✅ Implemented & tested
- Fact model with content-hash dedup
- WikiBackend Protocol + LocalFilesystemBackend (full CRUD)
- WikiStore: init/add_fact/add_facts/query/list_facts/rebuild_from_markdown/export
- Lossless Markdown render↔parse round-trip
- Deterministic bilingual regex extractor (7 patterns)
- 5 REST endpoints with Pydantic validation
- 53 tests (40 core + 13 API)

### 🔒 Reserved stubs (by design — not bugs)
- `HttpBackend.put_document/delete_document` → NotImplementedError (server deploy = Stage 8)
- `LLMFactExtractor.__init__` → NotImplementedError (LangGraph = Stage 3)
- ChromaDB vector index → hook only; query uses keyword relevance (drop-in upgrade later)

---

## 5. Test & Quality State

| Metric | Value |
|---|---|
| Total tests | 126 (was 73; +53 wiki) |
| Passing | 126 |
| Coverage (app/) | 92% |
| Coverage (wiki models/store/extractor) | 95–100% |
| ruff | clean |
| mypy strict | clean (23 source files) |

**Uncovered lines are intentional:** HttpBackend REST calls (requests not installed), singleton bootstrap (import-time), and a few defensive branches.

---

## 6. Unresolved Points & Risks

| ID | Item | Severity | Mitigation |
|---|---|---|---|
| R002 | HttpBackend writes raise NotImplementedError | low | REST contract documented; LocalFilesystemBackend covers all current needs |
| R003 | Vector index not wired; query is keyword-only | low | Sufficient for MVP; ChromaDB is a drop-in rebuild from Markdown |
| — | `LLMFactExtractor` not implemented | low | Deterministic extractor works; LLM extractor is a Stage 3 enhancement |

**No bugs.** All wiki tests passed on first run. Only fixes during dev:
- mypy: `str | None` in dict comprehension → walrus-filter in `list_all()`
- ruff E501: extracted `_post_fact()` helper in API tests to keep lines ≤100

---

## 7. Key Decisions This Stage (D006–D010)

| ID | Decision | Rationale |
|---|---|---|
| D006 | Markdown as source of truth; vector index derived | human-auditable, git-friendly, survives corruption |
| D007 | Pluggable WikiBackend Protocol | store code unchanged when server lands |
| D008 | Deterministic regex extractor default; LLM reserved | network-free tests; precision over recall |
| D009 | Fact dedup by content hash (case-folded SHA1[:16]) | re-extraction is no-op; case noise doesn't dupe |
| D010 | Wiki API in separate `wiki_routes.py` | one-domain-per-file; keeps `routes.py` focused |

---

## 8. Next Stage Options (pick by priority)

**Option A — Stage 3: LangGraph agent graph**
- Scaffold `app/core/graph/` with LangGraph nodes wrapping `routing_engine` + `wiki_store`
- Wire `LLMFactExtractor` once a model caller is available
- Connect: classify → respond → extract_facts → wiki.add_facts

**Option B — Dual-memory integration**
- `app/core/memory/session.py`: short-term session buffer (Redis or in-memory)
- Bridge: routing decision → session append → periodic extract → wiki
- Makes routing + wiki work together end-to-end

**Option C — Vector-indexed wiki query**
- Wire ChromaDB as derived index over Markdown
- Upgrade `query()` to semantic search (keep keyword as fallback)
- Unblocks R003

---

## 9. Pointers

| What | Path |
|---|---|
| This summary | `CONTEXT_SUMMARY_STAGE2.md` |
| Stage 1 summary | `CONTEXT_SUMMARY_STAGE1.md` |
| Progress tracker | `PROGRESS.yaml` |
| Latest checkpoint | `data/context/stage-2.cp.json` |
| Wiki module | `app/core/wiki/` |
| Wiki REST | `app/api/wiki_routes.py` |
