# Aether-Agent v2 — Context Management Rules

> **Purpose**: A concise, enforceable rulebook for managing dialogue context across single windows (auto-streamlining) and multiple windows (unified progress tracking). All templates are in JSON/YAML so any model can parse them in one shot.
>
> **Audience**: The implementing agent in the next dialogue window. Read this once at session start; reference templates as needed.

---

## 1. Core Principles

### 1.1 Context Is a Finite Resource

Every dialogue window has a finite context budget. Treating context as infinite leads to attention decay, forgotten decisions, and redundant re-derivation. The agent must actively manage context like memory: **compress what's stale, preserve what's decisive, discard what's recoverable from files**.

### 1.2 Files Are External Memory

Any artifact that exists in a file (code, configs, docs, PROGRESS.yaml) should NOT be duplicated verbatim in the dialogue context. The context should hold **pointers** (file paths + one-line summaries), not contents. If the model needs the contents, it reads the file. This single rule cuts context bloat by 60–80% in practice.

### 1.3 Decisions Are Sacred, Prose Is Disposable

When streamlining context, never lose a decision (what was chosen and why). Aggressively compress the discussion that led to the decision (the back-and-forth, the rejected alternatives). A future window needs to know "we chose Redis over Postgres for short-term memory because sub-ms latency is required" — it does NOT need the 8-message debate that preceded that choice.

### 1.4 Write Progress Before You Lose It

The agent must update `PROGRESS.yaml` at the end of every work session, not when the session ends naturally. Sessions end unpredictably (context limit, user closes window, network drop). Treat every commit as potentially the last — write progress first, then continue working.

### 1.5 Templates Over Prose

When transferring state between windows, use structured templates (JSON/YAML), not prose paragraphs. Prose is ambiguous, lossy, and requires the receiving model to re-parse. Structured data is exact, parseable in one token pass, and self-documenting via field names.

---

## 2. Single-Window Context Auto-Streamlining (NEW-1)

### 2.1 When to Streamline

Trigger a context streamline when ANY of these conditions hold:

| Trigger | Threshold | Action |
|---|---|---|
| Turn count | Every 5 user turns | Produce a `ContextCheckpoint` |
| Token estimate | >60% of window budget | Produce a `ContextCheckpoint` immediately |
| Stage completion | End of each implementation stage | Produce a `ContextCheckpoint` + update `PROGRESS.yaml` |
| User request | "summarize" / "checkpoint" | Produce a `ContextCheckpoint` immediately |

### 2.2 What to Preserve vs. Compress vs. Drop

| Content Type | Action | Rationale |
|---|---|---|
| Architectural decisions | **Preserve verbatim** (one line each) | Cannot be re-derived; losing them causes rework |
| File paths created/modified | **Preserve** (path + one-line purpose) | Pointer to external memory; recoverable by reading file |
| Current task + next action | **Preserve verbatim** | Continuity anchor for the model |
| Last 3 user messages | **Preserve verbatim** | Recent intent needed for coherent response |
| Rejected alternatives | **Compress** to "considered X, rejected because Y" | Decision context without the debate |
| Verbatim code blocks | **Drop** (they're in files now) | Recoverable by reading the file |
| Error tracebacks | **Drop** (keep only the fix) | The fix is the decision; the traceback is noise |
| Exploratory discussion | **Drop** | Was useful for reasoning; not needed for execution |
| Compliments / acknowledgments | **Drop** | Social noise; no execution value |

### 2.3 Streamline Protocol

When triggered, the agent executes these steps in order:

1. **Scan** the current context for decisions, file paths, and current task.
2. **Extract** decisions into a structured list (see template §4.1).
3. **Compress** the last 3 user intents into one line each.
4. **Drop** all verbatim code blocks older than the most recent file write.
5. **Emit** the `ContextCheckpoint` (see template §4.1).
6. **Save** the checkpoint to `data/context/{session_id}.cp.json`.
7. **Continue** the conversation with the checkpoint as the new context anchor.

### 2.4 Streamline Quality Checklist

Before finalizing a checkpoint, verify:

- [ ] Every architectural decision from the session is captured (one line each).
- [ ] Every file created/modified is listed with its current purpose.
- [ ] The "next action" is specific enough that a fresh model could execute it.
- [ ] No verbatim code block exceeds 3 lines (use file pointers instead).
- [ ] The checkpoint is <2KB (if larger, over-compression failed — re-scan).

---

## 3. Cross-Window Unified Progress Management (NEW-2)

### 3.1 The PROGRESS.yaml Contract

`PROGRESS.yaml` at the project root is the **single source of truth** for project state across windows. It is:

- **Machine-readable** — YAML, parseable in one shot by any model.
- **Agent-maintained** — the agent writes it; the user does not edit it manually.
- **Append-mostly** — fields are updated, rarely deleted; history is in git.
- **Idempotent** — reading it twice produces the same understanding.

### 3.2 Window Lifecycle Protocol

Every dialogue window follows this lifecycle:

```
Window Start
    │
    ▼
[1] Read PROGRESS.yaml  ← first action, before anything else
    │
    ▼
[2] Parse current phase + next action
    │
    ▼
[3] Read relevant files (only those needed for next action)
    │
    ▼
[4] Execute work (write code, run tests, etc.)
    │
    ▼
[5] Update PROGRESS.yaml  ← after every meaningful unit of work
    │
    ▼
[6] Git commit (stage completion or subtask completion)
    │
    ▼
[7] If context >60% full → streamline (see §2) + update PROGRESS.yaml
    │
    ▼
[8] If session ending → final PROGRESS.yaml update + commit
    │
    ▼
Window End
```

### 3.3 Resume Protocol (New Window)

When a new window opens for an existing project, the agent's first response must be:

1. Read `PROGRESS.yaml`.
2. Read the most recent `data/context/*.cp.json` (if exists).
3. Output a **Resume Brief** (see template §4.3) — a 5-line summary of where the project stands.
4. Ask the user to confirm the next action OR proceed if `next_action` is unambiguous.

This protocol eliminates the "what are we building again?" failure mode.

### 3.4 Concurrent Window Safety

If multiple windows might edit `PROGRESS.yaml` concurrently (rare but possible):

- Use file locking (`fcntl.flock` in Python) on every write.
- Include a `version` field; reject writes with stale version (optimistic locking).
- Last-writer-wins for non-conflicting fields; flag conflicts in a `conflicts` list.

For MVP, assume single-window-at-a-time. Document this assumption in `PROGRESS.yaml` itself.

---

## 4. Context Management Templates

All templates are designed for **one-shot model parsing**. Field names are self-documenting. Required fields are marked; optional fields have defaults.

### 4.1 ContextCheckpoint Template (NEW-1)

**File**: `data/context/{session_id}.cp.json`
**Purpose**: Compressed snapshot of a single window's state at a point in time.
**Trigger**: Every 5 turns OR >60% context usage OR stage completion.

```json
{
  "$schema": "context_checkpoint.v1",
  "session_id": "uuid-of-session",
  "created_at": "2026-06-21T14:30:00Z",
  "turn_count": 15,
  "trigger": "turn_threshold | token_threshold | stage_completion | user_request",

  "project_state": {
    "current_stage": "stage-2-memory",
    "stage_progress": "60%",
    "last_commit": "abc1234",
    "branch": "stage-2-memory"
  },

  "decisions": [
    {
      "id": "D001",
      "decision": "Use Redis for short-term memory (not Postgres)",
      "rationale": "Sub-ms latency required for chat; Redis TTL handles expiry natively",
      "alternatives_rejected": ["Postgres (too slow for hot path)", "in-process dict (lost on restart)"],
      "decided_at_turn": 3
    },
    {
      "id": "D002",
      "decision": "Markdown is source of truth, ChromaDB is derived index",
      "rationale": "Human-auditable + git-friendly; ChromaDB rebuildable from markdown",
      "alternatives_rejected": ["ChromaDB-only (not human-editable)"],
      "decided_at_turn": 7
    }
  ],

  "files": [
    {"path": "app/core/memory.py", "purpose": "Redis short-term memory wrapper", "status": "in_progress"},
    {"path": "app/core/wiki.py", "purpose": "Markdown + ChromaDB long-term store", "status": "not_started"},
    {"path": "app/core/routing/router.py", "purpose": "Routing engine (Stage 1, done)", "status": "done"}
  ],

  "recent_intents": [
    {"turn": 13, "user_intent": "implement Redis memory append with sliding window"},
    {"turn": 14, "user_intent": "add TTL to session keys"},
    {"turn": 15, "user_intent": "write tests for memory module"}
  ],

  "current_task": {
    "description": "Write tests/test_memory.py covering append, trim, TTL expiry",
    "started_at_turn": 15,
    "blockers": []
  },

  "next_action": {
    "description": "Run pytest tests/test_memory.py and fix failures",
    "expected_output": "All tests green; commit with message 'test(memory): add session lifecycle tests'"
  },

  "dropped_content_summary": "Compressed 8 messages of Redis-vs-Postgres debate into D001. Dropped 3 verbatim code blocks (now in app/core/memory.py)."
}
```

### 4.2 PROGRESS.yaml Template (NEW-2)

**File**: `PROGRESS.yaml` (project root)
**Purpose**: Single source of truth for cross-window project state.
**Updated**: After every meaningful unit of work (not just stage completion).

```yaml
# =============================================================================
# Aether-Agent v2 — Cross-Window Progress Tracker
# =============================================================================
# This file is the SINGLE SOURCE OF TRUTH for project state.
# - New windows read this first (before any other action).
# - The agent updates this after every meaningful unit of work.
# - Users do NOT edit this manually (the agent maintains it).
# =============================================================================

$schema: progress.v1
project_name: aether-agent-v2
project_version: 0.2.0
last_updated: "2026-06-21T14:30:00Z"
last_updated_by: "agent-session-uuid"
last_window_id: "window-uuid"

# --- High-level state ---
current_stage: stage-2-memory
overall_progress: 35%   # (completed_stages / total_stages) * 100

# --- Stage status ---
stages:
  stage-0-foundation:
    status: done
    started_at: "2026-06-21T09:00:00Z"
    completed_at: "2026-06-21T10:00:00Z"
    commit: "abc1234"
    notes: "Docker + CI skeleton working"
  stage-1-routing:
    status: done
    started_at: "2026-06-21T10:00:00Z"
    completed_at: "2026-06-21T13:00:00Z"
    commit: "def5678"
    notes: "36 routing tests passing; zero-LLM routing engine complete"
  stage-2-memory:
    status: in_progress
    started_at: "2026-06-21T13:00:00Z"
    completed_at: null
    commit: null
    notes: "Redis memory done; wiki module in progress"
    subtasks:
      - id: 2.1
        name: "Redis short-term memory"
        status: done
      - id: 2.2
        name: "Markdown + ChromaDB wiki"
        status: in_progress
      - id: 2.3
        name: "Persona builder"
        status: not_started
      - id: 2.4
        name: "Tests for memory + wiki"
        status: not_started
  stage-3-graph:
    status: not_started
  stage-4-context:
    status: not_started
  stage-5-progress:
    status: not_started
  stage-6-tasks:
    status: not_started
  stage-7-api-docs:
    status: not_started
  stage-8-cicd-deploy:
    status: not_started

# --- Key decisions (mirrors latest ContextCheckpoint) ---
key_decisions:
  - id: D001
    decision: "Use Redis for short-term memory"
    rationale: "Sub-ms latency; native TTL"
  - id: D002
    decision: "Markdown is source of truth, ChromaDB is derived"
    rationale: "Human-auditable; rebuildable"
  - id: D003
    decision: "Zero-LLM deterministic routing"
    rationale: "Saves 100% classification cost + 200ms latency"

# --- Environment state ---
environment:
  python_version: "3.12.13"
  os: "Linux 5.10"
  redis_running: true
  chroma_initialized: true
  local_llm_available: false   # Ollama not running
  env_file_present: true
  env_keys_set:
    OPENAI_API_KEY: true
    REDIS_URL: true
    CHROMA_PERSIST_DIR: true

# --- Test state ---
tests:
  total: 36
  passing: 36
  failing: 0
  last_run: "2026-06-21T14:25:00Z"
  coverage: 82%

# --- Blockers / risks ---
blockers: []
risks:
  - id: R001
    description: "Local Llama-3-8B not running; PARSE tier falls back to CHAT"
    severity: low
    mitigation: "Document in README; user can start Ollama if needed"

# --- Next action (CRITICAL — this is what the next window reads first) ---
next_action:
  description: "Complete app/core/wiki.py: implement Markdown read/write + ChromaDB embedding + LLM extractor"
  expected_output: "wiki_store.init() works; can add_fact() and query() back; extract_from_turns() returns facts"
  estimated_steps:
    - "Write WikiStore class with init(), add_fact(), query()"
    - "Write extract_from_turns() using LLM with JSON output"
    - "Write rebuild_from_markdown() for disaster recovery"
    - "Run tests/test_wiki.py (write it first)"

# --- Pointers (do NOT inline contents — just paths) ---
pointers:
  latest_checkpoint: "data/context/session-abc.cp.json"
  task_ledger: "TASKS.jsonl"
  routing_policy: "enterprise_routing.example.yaml"
  api_docs: "docs/API.md"
  deployment_docs: "docs/DEPLOYMENT.md"
```

### 4.3 Resume Brief Template (NEW-2)

**Purpose**: The 5-line summary a new window outputs after reading `PROGRESS.yaml`.
**Format**: Plain text (not JSON) — it's for the user to read, not for machines.

```
[Resume Brief]
Project: aether-agent-v2 (v0.2.0)
Stage: stage-2-memory (in_progress, 35% overall)
Last work: Redis short-term memory complete (commit def5678)
Next action: Complete app/core/wiki.py — Markdown + ChromaDB + LLM extractor
Blockers: none
```

The agent outputs this verbatim, then asks: "Shall I proceed with the next action, or do you want to adjust?"

### 4.4 TaskLedger Entry Template (NEW-3)

**File**: `TASKS.jsonl` (project root, append-only)
**Purpose**: Track parallel subtasks across multiple agents.
**Format**: One JSON object per line (JSONL — concurrent-safe appends).

```json
{"id": "T001", "owner": "agent-1", "type": "implementation", "description": "Implement app/core/memory.py", "status": "done", "started_at": "2026-06-21T13:00:00Z", "finished_at": "2026-06-21T13:45:00Z", "artifact": "app/core/memory.py", "result": "success", "commit": "def5678"}
{"id": "T002", "owner": "agent-2", "type": "test", "description": "Write tests/test_memory.py", "status": "running", "started_at": "2026-06-21T13:46:00Z", "finished_at": null, "artifact": "tests/test_memory.py", "result": null, "commit": null}
{"id": "T003", "owner": "agent-3", "type": "docs", "description": "Write docs/API.md", "status": "pending", "started_at": null, "finished_at": null, "artifact": "docs/API.md", "result": null, "commit": null}
```

**Field semantics**:
- `status`: `pending` (not started) | `running` (in progress) | `done` (completed successfully) | `failed` (completed with error) | `orphaned` (timed out during finalization)
- `result`: `success` | `failure` | `partial` | null (while running)
- `artifact`: relative path to the primary output file (may be null for non-code tasks)

### 4.5 Finalization Report Template (NEW-3)

**File**: `data/finalization_report_{timestamp}.json`
**Purpose**: Summary of project-end state, including async task resolution.
**Trigger**: `scripts/finalize.py` execution.

```json
{
  "$schema": "finalization_report.v1",
  "generated_at": "2026-06-21T18:00:00Z",
  "project_name": "aether-agent-v2",
  "project_version": "0.2.0",

  "stage_completion": {
    "total_stages": 9,
    "completed": 9,
    "in_progress": 0,
    "not_started": 0,
    "completion_rate": "100%"
  },

  "task_ledger_summary": {
    "total_tasks": 24,
    "done": 22,
    "failed": 1,
    "orphaned": 1,
    "orphaned_details": [
      {
        "id": "T019",
        "description": "Run full integration test suite",
        "orphan_reason": "Timed out after 60s (likely hanging on Redis connection)",
        "recommended_action": "Check Redis availability; re-run manually"
      }
    ]
  },

  "test_state": {
    "total": 48,
    "passing": 47,
    "failing": 1,
    "failing_tests": ["tests/test_wiki.py::test_extract_with_network_error"],
    "coverage": "84%"
  },

  "artifacts": {
    "docker_image": "ghcr.io/org/aether-agent:0.2.0",
    "git_tag": "v0.2.0",
    "release_notes": "CHANGELOG.md"
  },

  "known_issues": [
    {
      "severity": "low",
      "description": "Local Llama-3-8B not running; PARSE tier falls back to CHAT",
      "workaround": "Start Ollama or accept higher token cost"
    }
  ],

  "next_steps_recommended": [
    "Fix failing test test_extract_with_network_error",
    "Enable streaming responses (v2.1 roadmap)",
    "Add authentication layer (v2.1 roadmap)"
  ]
}
```

### 4.6 Multi-Agent Status Board Template (NEW-3)

**Purpose**: Live snapshot of parallel agents working on the same project.
**Format**: In-memory or Redis-backed; rendered as JSON on demand.
**Use case**: When 3+ agents work in parallel, the orchestrator polls this to detect stragglers.

```json
{
  "$schema": "agent_status_board.v1",
  "snapshot_at": "2026-06-21T14:45:00Z",
  "active_agents": 3,
  "agents": [
    {
      "agent_id": "agent-1",
      "current_task_id": "T005",
      "task_description": "Implement app/core/wiki.py",
      "status": "running",
      "started_at": "2026-06-21T14:00:00Z",
      "heartbeat_at": "2026-06-21T14:44:30Z",
      "progress_hint": "60% — WikiStore class done, extractor in progress"
    },
    {
      "agent_id": "agent-2",
      "current_task_id": "T006",
      "task_description": "Write tests/test_wiki.py",
      "status": "running",
      "started_at": "2026-06-21T14:15:00Z",
      "heartbeat_at": "2026-06-21T14:45:00Z",
      "progress_hint": "30% — 4 of 12 tests written"
    },
    {
      "agent_id": "agent-3",
      "current_task_id": "T007",
      "task_description": "Write docs/API.md",
      "status": "idle",
      "started_at": null,
      "heartbeat_at": "2026-06-21T14:30:00Z",
      "progress_hint": "Waiting for T005 to complete (needs final API surface)"
    }
  ],
  "stragglers": [],
  "blocked_tasks": [
    {
      "task_id": "T007",
      "blocked_by": "T005",
      "reason": "API surface not finalized"
    }
  ]
}
```

---

## 5. Trigger Conditions (Quick Reference)

| Event | Template Produced | File Written |
|---|---|---|
| Every 5 user turns | ContextCheckpoint (§4.1) | `data/context/{session_id}.cp.json` |
| >60% context usage | ContextCheckpoint (§4.1) | `data/context/{session_id}.cp.json` |
| Stage completion | PROGRESS.yaml update (§4.2) | `PROGRESS.yaml` |
| Subtask completion | PROGRESS.yaml update (§4.2) | `PROGRESS.yaml` |
| New window opens | Resume Brief (§4.3) output to user | (none — displayed only) |
| Parallel subtask starts | TaskLedger entry (§4.4) | `TASKS.jsonl` (append) |
| Parallel subtask ends | TaskLedger entry update (§4.4) | `TASKS.jsonl` (append new line) |
| Project finalization | Finalization Report (§4.5) | `data/finalization_report_{ts}.json` |
| Multi-agent polling | Status Board (§4.6) | (in-memory or Redis, not file) |

---

## 6. Validation Checklist

Before claiming a context management operation is complete, verify:

### 6.1 ContextCheckpoint Validation
- [ ] All decisions from the session are captured (one line each).
- [ ] Every file created/modified is listed with current purpose.
- [ ] `next_action` is specific enough for a fresh model to execute.
- [ ] No verbatim code block >3 lines (use file pointers).
- [ ] Checkpoint file is <2KB.
- [ ] `dropped_content_summary` explains what was compressed/dropped.

### 6.2 PROGRESS.yaml Validation
- [ ] `last_updated` timestamp is current.
- [ ] `current_stage` matches actual work in progress.
- [ ] `next_action.description` is actionable (not "continue working").
- [ ] All completed stages have `commit` SHA.
- [ ] `environment` section reflects actual runtime state.
- [ ] `tests` section reflects most recent test run.
- [ ] No field contains prose >1 sentence (use `notes` for exceptions).

### 6.3 TaskLedger Validation
- [ ] Every `running` task has a recent `heartbeat_at` (within 5 minutes).
- [ ] No two tasks have the same `id`.
- [ ] Every `done` task has `finished_at` + `result` + `commit`.
- [ ] Every `failed` task has `result: failure` + a note in `artifact` or a linked issue.

### 6.4 Finalization Report Validation
- [ ] `stage_completion.completion_rate` matches actual stage statuses.
- [ ] Every `orphaned` task has `orphan_reason` + `recommended_action`.
- [ ] `test_state.failing_tests` lists every failing test by full name.
- [ ] `next_steps_recommended` has ≥1 item (even if project is "done").

---

## 7. Anti-Patterns to Avoid

### 7.1 Context Anti-Patterns

- **Prose progress reports**: "We made good progress today on the memory module..." → Use structured `PROGRESS.yaml` instead.
- **Verbatim code in context**: Pasting a 50-line function into the chat → Reference the file path instead.
- **Decision re-derivation**: Re-explaining why Redis was chosen in every window → Capture once in `key_decisions`, reference forever.
- **Stale checkpoints**: A `ContextCheckpoint` from 3 sessions ago still in context → Drop it; `PROGRESS.yaml` supersedes it.

### 7.2 Progress Tracking Anti-Patterns

- **Vague next actions**: "Continue working on memory" → Use "Write tests/test_memory.py covering append, trim, TTL".
- **Manual user updates**: Asking the user to maintain progress → The agent maintains it; the user only reviews.
- **Multiple progress files**: `progress.txt`, `TODO.md`, `STATUS.md` all coexisting → One file: `PROGRESS.yaml`.
- **No git commits between updates**: PROGRESS.yaml updated but not committed → If the window dies, the update is lost.

### 7.3 Multi-Agent Anti-Patterns

- **Synchronous waiting**: Agent A blocks on Agent B's completion → Use the task ledger; A should pick a different task.
- **No heartbeats**: Long-running task with no status update → Require heartbeat every 5 minutes; flag stragglers.
- **Silent failures**: Task fails but ledger not updated → Wrap every task in try/except that writes `status: failed` to ledger.
- **Orphan ignoring**: Finalization report lists orphans but nobody acts on them → Orphans must have `recommended_action` and be tracked in the next session's `PROGRESS.yaml.blockers`.

---

## 8. Integration with Implementation Plan

This document pairs with `Aether_Agent_v2_Implementation_Plan.md`. The mapping:

| Implementation Plan Section | Context Management Rule |
|---|---|
| §1.2 NEW-1 (single-window streamlining) | §2 (this doc) + Template §4.1 |
| §1.2 NEW-2 (cross-window progress) | §3 (this doc) + Template §4.2, §4.3 |
| §1.2 NEW-3 (multi-agent + finalization) | Template §4.4, §4.5, §4.6 |
| §3 Stage 4 (Context module) | Implements §2 + §4.1 |
| §3 Stage 5 (Progress module) | Implements §3 + §4.2, §4.3 |
| §3 Stage 6 (Tasks module) | Implements §4.4, §4.5, §4.6 |
| §13 Self-validation | §6 Validation checklist (this doc) |

The implementing agent should read both documents at session start, then reference templates as needed during execution. The templates are designed to be copy-pasted and filled in — they are not abstract specifications.

---

## 9. Minimal Constraint Statement

These rules are deliberately minimal. They specify **what** must be tracked and **how** it must be structured, but NOT:

- How often the agent should think or pause (that's the agent's judgment).
- Which specific model to use for extraction (any capable model works).
- Whether to use streaming or batch for LLM calls (implementation choice).
- How to format code (ruff handles that).
- How to name variables (the agent's discretion, within ruff rules).

The goal is to make context transfer between windows **reliable and lossless**, not to constrain the agent's working style. A capable model should be able to read these two documents, read `PROGRESS.yaml`, and resume work with zero additional context.
