import math
from r10s3pkg import InvertedIndex, TextAnalyzer


def test_boolean_and_not_filtering():
    idx = InvertedIndex()
    idx.add_document("d1", "distributed storage engine for cloud")
    idx.add_document("d2", "distributed storage engine for edge")
    idx.add_document("d3", "local storage engine")

    res = idx.search("distributed storage -edge")
    assert [r.doc_id for r in res] == ["d1"]


def test_tf_idf_ranking_and_tie_breaking():
    idx = InvertedIndex()
    idx.add_document("b_doc", "kernel router")
    idx.add_document("a_doc", "kernel router")
    idx.add_document("c_doc", "kernel router kernel")

    res = idx.search("kernel router")
    assert [r.doc_id for r in res] == ["c_doc", "a_doc", "b_doc"]
    assert res[0].score > res[1].score
    assert res[1].score == res[2].score


def test_remove_document_updates_count_and_postings():
    idx = InvertedIndex()
    idx.add_document("d1", "alpha beta")
    idx.add_document("d2", "beta gamma")
    assert idx.doc_count == 2

    assert idx.remove_document("d1") is True
    assert idx.remove_document("d1") is False
    assert idx.doc_count == 1
    assert idx.search("alpha") == []
    assert [r.doc_id for r in idx.search("beta")] == ["d2"]


def test_empty_or_stopword_only_query():
    idx = InvertedIndex()
    idx.add_document("d1", "the quick brown fox")
    assert idx.search("") == []
    assert idx.search("the of and") == []
    assert idx.search('"the of"') == []


def test_tokenize_preserves_stopword_position_gaps():
    analyzer = TextAnalyzer()
    tokens = analyzer.tokenize("state of the art")
    assert [(t.term, t.position) for t in tokens] == [("state", 0), ("art", 3)]


def test_phrase_query_with_stopword_gaps_enforces_exact_distance():
    idx = InvertedIndex()
    idx.add_document("exact_gap", "we build state of the art systems")
    idx.add_document("no_gap", "we build state art systems")
    idx.add_document("single_gap", "we build state of art systems")

    res_two_gap = idx.search('"state of the art"')
    assert [r.doc_id for r in res_two_gap] == ["exact_gap"]

    res_no_gap = idx.search('"state art"')
    assert [r.doc_id for r in res_no_gap] == ["no_gap"]


def test_phrase_with_leading_stopword_and_boolean_term():
    idx = InvertedIndex()
    idx.add_document("d1", " journey to the center of earth")
    idx.add_document("d2", "journey center earth")

    res = idx.search('"the center of earth" journey')
    assert [r.doc_id for r in res] == ["d1"]


def test_reindex_existing_document_purges_stale_terms():
    idx = InvertedIndex()
    idx.add_document("doc1", "legacy monolith architecture")
    idx.add_document("doc2", "modern service architecture")

    idx.add_document("doc1", "modern cloud architecture")

    assert idx.doc_count == 2
    assert idx.search("legacy") == []
    assert idx.search("monolith") == []
    assert [r.doc_id for r in idx.search("cloud")] == ["doc1"]


def test_reindex_existing_document_replaces_positions_and_scores():
    idx = InvertedIndex()
    idx.add_document("doc1", "alpha beta alpha beta")
    idx.add_document("doc2", "alpha beta")

    idx.add_document("doc1", "beta alpha")

    assert idx.doc_count == 2
    assert [r.doc_id for r in idx.search('"alpha beta"')] == ["doc2"]

    res = idx.search("alpha")
    expected_score = round(1 * math.log(1.0 + (2 / 2)), 6)
    assert len(res) == 2
    assert res[0].score == expected_score
    assert res[1].score == expected_score
