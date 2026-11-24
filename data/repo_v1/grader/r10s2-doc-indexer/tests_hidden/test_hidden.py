import pytest
from r10s2idx import InvertedIndex, QueryEngine, Tokenizer


def test_stemming_and_boolean_ranking():
    idx = InvertedIndex()
    idx.upsert_document("doc_a", "indexing indexed indexes search")
    idx.upsert_document("doc_b", "searching indexers systems")
    idx.upsert_document("doc_c", "unrelated network router")

    engine = QueryEngine(idx)
    results = engine.search(must_terms=["index"], should_terms=["searching"])
    assert [r.doc_id for r in results] == ["doc_a"]
    assert results[0].score > 0


def test_delete_document_removes_from_search():
    idx = InvertedIndex()
    idx.upsert_document("d1", "consensus protocol")
    idx.upsert_document("d2", "consensus engine")
    assert idx.delete_document("d1") is True
    assert idx.delete_document("d1") is False

    engine = QueryEngine(idx)
    res = engine.search(must_terms=["consensus"])
    assert [r.doc_id for r in res] == ["d2"]


def test_stale_version_rejected():
    idx = InvertedIndex()
    assert idx.upsert_document("d1", "alpha beta", version=5) is True
    assert idx.upsert_document("d1", "gamma delta", version=3) is False

    engine = QueryEngine(idx)
    assert [r.doc_id for r in engine.search(must_terms=["alpha"])] == ["d1"]
    assert engine.search(must_terms=["gamma"]) == []


def test_tokenize_preserves_original_word_positions_across_stopwords():
    tok = Tokenizer()
    tokens = tok.tokenize_with_positions("State of the art in search")
    assert tokens == [("state", 0), ("art", 3), ("search", 5)]


def test_phrase_query_respects_stopword_gaps():
    idx = InvertedIndex()
    idx.upsert_document("d_exact", "we build state of the art search engines")
    idx.upsert_document("d_adjacent", "we build state art search engines")
    idx.upsert_document("d_wrong_gap", "we build state of art search engines")

    engine = QueryEngine(idx)
    assert engine.match_phrase("state of the art") == {"d_exact"}
    assert engine.match_phrase("state art") == {"d_adjacent"}


def test_multi_step_search_combining_stopword_phrase_and_boolean():
    idx = InvertedIndex()
    idx.upsert_document("d1", "introduction to the system and architecture")
    idx.upsert_document("d2", "introduction system architecture")
    idx.upsert_document("d3", "introduction to the system legacy")

    engine = QueryEngine(idx)
    results = engine.search(
        phrases=["introduction to the system"],
        not_terms=["legacy"],
    )
    assert [r.doc_id for r in results] == ["d1"]


def test_upsert_replaces_old_postings_cleanly():
    idx = InvertedIndex()
    idx.upsert_document("d1", "legacy monolith server", version=1)
    idx.upsert_document("d1", "modern microservice gateway", version=2)

    engine = QueryEngine(idx)
    assert engine.search(must_terms=["legacy"]) == []
    assert "legacy" not in idx.postings
    assert [r.doc_id for r in engine.search(must_terms=["modern"])] == ["d1"]
    assert idx.term_positions("modern", "d1") == [0]


def test_upsert_same_term_does_not_accumulate_duplicate_positions():
    idx = InvertedIndex()
    idx.upsert_document("d1", "kernel module", version=1)
    idx.upsert_document("d1", "driver kernel", version=2)

    assert idx.term_positions("kernel", "d1") == [1]
    engine = QueryEngine(idx)
    assert engine.match_phrase("kernel module") == set()
    assert engine.match_phrase("driver kernel") == {"d1"}


def test_batch_rollback_restores_deep_postings_state():
    idx = InvertedIndex()
    idx.upsert_document("d1", "storage engine transaction", version=1)

    idx.begin_batch()
    idx.upsert_document("d1", "corrupted payload", version=2)
    idx.upsert_document("d2", "storage network", version=1)
    idx.rollback_batch()

    engine = QueryEngine(idx)
    assert "d2" not in idx.documents
    assert idx.documents["d1"].version == 1
    assert engine.search(must_terms=["corrupted"]) == []
    assert [r.doc_id for r in engine.search(must_terms=["transaction"])] == ["d1"]
    assert idx.docs_for_term("storage") == {"d1"}
    assert idx.term_positions("storage", "d1") == [0]
