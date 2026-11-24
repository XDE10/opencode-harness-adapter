from r10s2idx import InvertedIndex, QueryEngine


def test_basic_insert_and_term_query():
    idx = InvertedIndex()
    idx.upsert_document("d1", "distributed consensus systems")
    idx.upsert_document("d2", "distributed database storage")

    engine = QueryEngine(idx)
    res = engine.search(must_terms=["distributed"], not_terms=["storage"])
    assert [r.doc_id for r in res] == ["d1"]


def test_simple_adjacent_phrase_query():
    idx = InvertedIndex()
    idx.upsert_document("d1", "fast inverted index builder")
    idx.upsert_document("d2", "inverted fast builder index")

    engine = QueryEngine(idx)
    assert engine.match_phrase("inverted index") == {"d1"}
