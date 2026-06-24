"""Tests for app.core.wiki — Fact model, store, backends, extractor.

Covers: content-hash dedup, Markdown round-trip serialization, add/query/list,
rebuild, export, LocalFilesystemBackend CRUD, and deterministic extraction.
All tests are network/LLM-free.
"""

from __future__ import annotations

from app.core.wiki.backends import LocalFilesystemBackend
from app.core.wiki.extractor import extract_from_turns
from app.core.wiki.models import Fact, WikiQueryResult
from app.core.wiki.store import (
    WikiStore,
    _doc_name,
    _parse_markdown,
    _relevance,
    _render_markdown,
)

# --- Fact model ---


def test_fact_id_is_stable_content_hash():
    """Same content -> same id, regardless of unrelated fields."""
    f1 = Fact(subject="user", predicate="prefers", object="dark mode")
    f2 = Fact(subject="user", predicate="prefers", object="dark mode", source="manual")
    assert f1.id == f2.id
    assert f1.id  # non-empty


def test_fact_id_differs_for_different_content():
    f1 = Fact(subject="user", predicate="prefers", object="dark mode")
    f2 = Fact(subject="user", predicate="prefers", object="light mode")
    assert f1.id != f2.id


def test_fact_id_case_insensitive():
    """Hash is case-folded so capitalization noise doesn't create dupes."""
    f1 = Fact(subject="User", predicate="Prefers", object="Dark Mode")
    f2 = Fact(subject="user", predicate="prefers", object="dark mode")
    assert f1.id == f2.id


def test_fact_explicit_id_preserved():
    f = Fact(subject="x", predicate="y", object="z", id="custom-id")
    assert f.id == "custom-id"


def test_fact_defaults():
    f = Fact(subject="user", predicate="name", object="Alice")
    assert f.source == "extracted"
    assert f.confidence == 1.0
    assert f.tags == []
    assert f.created_at > 0


# --- Markdown round-trip ---


def test_render_then_parse_round_trips():
    """A rendered document must parse back to equivalent facts."""
    original = [
        Fact(subject="user", predicate="prefers", object="dark mode", tags=["ui"]),
        Fact(subject="user", predicate="uses", object="python"),
    ]
    md = _render_markdown("user", original)
    parsed = _parse_markdown(md)
    assert len(parsed) == 2
    # Each parsed fact should hash-collide with its original (same content).
    parsed_ids = {f.id for f in parsed}
    original_ids = {f.id for f in original}
    assert parsed_ids == original_ids


def test_render_includes_subject_heading_and_bullets():
    md = _render_markdown("user", [Fact(subject="user", predicate="uses", object="python")])
    assert md.startswith("# user")
    assert "- uses: python" in md


def test_render_tags_rendered_in_brackets():
    f = Fact(subject="user", predicate="prefers", object="vim", tags=["editor", "tools"])
    md = _render_markdown("user", [f])
    assert "[editor, tools]" in md


def test_parse_extracts_tags():
    md = "# user\n\n- prefers: vim  [editor, tools]\n"
    facts = _parse_markdown(md)
    assert len(facts) == 1
    assert facts[0].tags == ["editor", "tools"]


def test_parse_skips_lines_without_subject():
    md = "- orphan: no subject yet\n\n# user\n\n- uses: python\n"
    facts = _parse_markdown(md)
    assert len(facts) == 1
    assert facts[0].subject == "user"


def test_doc_name_slugifies():
    assert _doc_name("user") == "user"
    assert _doc_name("Project Alpha") == "project-alpha"


# --- WikiStore writes ---


def _store(tmp_path) -> WikiStore:
    backend = LocalFilesystemBackend(tmp_path / "wiki")
    store = WikiStore(backend)
    store.init()
    return store


def test_add_fact_returns_true_for_new_fact(tmp_path):
    store = _store(tmp_path)
    fact = Fact(subject="user", predicate="name", object="Alice")
    assert store.add_fact(fact) is True


def test_add_fact_dedups(tmp_path):
    store = _store(tmp_path)
    fact = Fact(subject="user", predicate="name", object="Alice")
    assert store.add_fact(fact) is True
    assert store.add_fact(fact) is False  # same id -> ignored
    assert len(store.list_facts()) == 1


def test_add_facts_returns_count_of_new(tmp_path):
    store = _store(tmp_path)
    facts = [
        Fact(subject="user", predicate="name", object="Alice"),
        Fact(subject="user", predicate="uses", object="python"),
    ]
    assert store.add_facts(facts) == 2
    # Adding again (plus a dup of one) -> 0 new.
    assert store.add_facts(facts) == 0


def test_add_fact_persists_to_markdown(tmp_path):
    store = _store(tmp_path)
    store.add_fact(Fact(subject="user", predicate="name", object="Alice"))
    # A new store reading the same backend must see the fact.
    store2 = WikiStore(LocalFilesystemBackend(store.backend.root))  # type: ignore[attr-defined]
    store2.init()
    assert any(f.object == "Alice" for f in store2.list_facts())


# --- WikiStore reads ---


def test_query_exact_substring_scores_highest(tmp_path):
    store = _store(tmp_path)
    store.add_fact(Fact(subject="user", predicate="uses", object="python 3.12"))
    results = store.query("python 3.12")
    assert results
    assert results[0].score == 1.0
    assert results[0].fact.object == "python 3.12"


def test_query_returns_empty_for_no_match(tmp_path):
    store = _store(tmp_path)
    store.add_fact(Fact(subject="user", predicate="uses", object="python"))
    assert store.query("quantum mechanics") == []


def test_query_orders_by_relevance(tmp_path):
    store = _store(tmp_path)
    store.add_fact(Fact(subject="user", predicate="uses", object="python"))
    store.add_fact(Fact(subject="user", predicate="prefers", object="dark mode python"))
    results = store.query("python")
    # Both match; the one where 'python' is the object (exact substring) leads.
    assert results[0].score >= results[1].score


def test_query_respects_limit(tmp_path):
    store = _store(tmp_path)
    for i in range(10):
        store.add_fact(Fact(subject="user", predicate="uses", object=f"python tool {i}"))
    results = store.query("python", limit=3)
    assert len(results) <= 3


def test_list_facts_filters_by_subject(tmp_path):
    store = _store(tmp_path)
    store.add_fact(Fact(subject="user", predicate="name", object="Alice"))
    store.add_fact(Fact(subject="project", predicate="uses", object="python"))
    assert len(store.list_facts(subject="user")) == 1
    assert len(store.list_facts(subject="project")) == 1
    assert len(store.list_facts()) == 2


# --- maintenance ---


def test_rebuild_from_markdown(tmp_path):
    store = _store(tmp_path)
    store.add_fact(Fact(subject="user", predicate="name", object="Alice"))
    count = store.rebuild_from_markdown()
    assert count == 1


def test_export_returns_all_documents(tmp_path):
    store = _store(tmp_path)
    store.add_fact(Fact(subject="user", predicate="name", object="Alice"))
    store.add_fact(Fact(subject="project", predicate="uses", object="python"))
    exported = store.export()
    assert "user" in exported
    assert "project" in exported
    assert "Alice" in exported["user"]


# --- relevance helper ---


def test_relevance_exact_match_is_one():
    f = Fact(subject="user", predicate="uses", object="python")
    assert _relevance(f, "python") == 1.0


def test_relevance_no_overlap_is_zero():
    f = Fact(subject="user", predicate="uses", object="python")
    assert _relevance(f, "quantum") == 0.0


def test_relevance_partial_overlap_between_zero_and_one():
    f = Fact(subject="user", predicate="uses", object="python language")
    score = _relevance(f, "python rocks")
    assert 0.0 < score < 1.0


# --- LocalFilesystemBackend CRUD ---


def test_backend_put_get_round_trip(tmp_path):
    backend = LocalFilesystemBackend(tmp_path / "wiki")
    backend.put_document("user", "# user\n\n- uses: python\n")
    assert backend.get_document("user") == "# user\n\n- uses: python\n"


def test_backend_get_missing_returns_none(tmp_path):
    backend = LocalFilesystemBackend(tmp_path / "wiki")
    assert backend.get_document("nope") is None


def test_backend_list_documents(tmp_path):
    backend = LocalFilesystemBackend(tmp_path / "wiki")
    backend.put_document("user", "# user")
    backend.put_document("project", "# project")
    assert backend.list_documents() == ["project", "user"]


def test_backend_delete(tmp_path):
    backend = LocalFilesystemBackend(tmp_path / "wiki")
    backend.put_document("user", "# user")
    assert backend.delete_document("user") is True
    assert backend.delete_document("user") is False  # already gone
    assert backend.get_document("user") is None


def test_backend_list_all(tmp_path):
    backend = LocalFilesystemBackend(tmp_path / "wiki")
    backend.put_document("user", "# user")
    backend.put_document("project", "# project")
    all_docs = backend.list_all()
    assert set(all_docs.keys()) == {"user", "project"}


def test_backend_creates_root_dir(tmp_path):
    root = tmp_path / "nested" / "wiki"
    assert not root.exists()
    LocalFilesystemBackend(root)
    assert root.exists()


# --- extractor ---


def test_extract_from_turns_catches_name_pattern():
    facts = extract_from_turns(["my name is Alice and I like tea"])
    names = [f for f in facts if f.predicate == "name"]
    assert names
    assert names[0].object == "Alice"


def test_extract_from_turns_catches_preference():
    facts = extract_from_turns(["I prefer dark mode."])
    prefs = [f for f in facts if f.predicate == "prefers"]
    assert prefs
    assert "dark mode" in prefs[0].object


def test_extract_from_turns_catches_uses():
    facts = extract_from_turns(["I use python for everything"])
    uses = [f for f in facts if f.predicate == "uses"]
    assert uses


def test_extract_from_turns_catches_project_pattern():
    facts = extract_from_turns(["the project uses FastAPI"])
    proj = [f for f in facts if f.subject == "project"]
    assert proj


def test_extract_from_turns_dedups_across_turns():
    facts = extract_from_turns(
        ["my name is Alice", "my name is Alice again"]
    )
    names = [f for f in facts if f.predicate == "name" and f.object == "Alice"]
    assert len(names) == 1


def test_extract_from_turns_assigns_confidence_and_source():
    facts = extract_from_turns(["I prefer vim"], confidence=0.42)
    assert facts
    assert facts[0].confidence == 0.42
    assert facts[0].source == "extracted"


def test_extract_from_turns_ignores_empty():
    assert extract_from_turns([]) == []
    assert extract_from_turns(["nothing matches here at all"]) == []


def test_extract_from_turns_rejects_oversized_capture():
    """A pathological >200 char capture should be dropped."""
    long_value = "x" * 300
    facts = extract_from_turns([f"I prefer {long_value}."])
    assert facts == []


# --- integration: extract -> store -> query ---


def test_extract_then_store_then_query(tmp_path):
    store = _store(tmp_path)
    facts = extract_from_turns(["I use python", "my name is Alice"])
    added = store.add_facts(facts)
    assert added >= 2
    hits = store.query("python")
    assert hits
    assert WikiQueryResult  # imported symbol is the public type
