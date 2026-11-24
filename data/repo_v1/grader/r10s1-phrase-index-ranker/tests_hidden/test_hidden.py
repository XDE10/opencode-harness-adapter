import math
from docsearch import SearchIndex, parse_query, tokenize


def test_tokenize_preserves_stream_positions_across_stopwords():
    tokens = tokenize("State of the art search in a box")
    assert [(t.term, t.position) for t in tokens] == [
        ("state", 0),
        ("art", 3),
        ("search", 4),
        ("box", 7),
    ]


def test_parse_query_preserves_phrase_offsets_with_stopwords():
    pq = parse_query('"state of the art" -legacy system')
    assert pq.phrases == [[("state", 0), ("art", 3)]]
    assert pq.required_terms == ["system"]
    assert pq.excluded_terms == ["legacy"]


def test_phrase_search_does_not_false_match_across_stopword_gap():
    idx = SearchIndex()
    idx.add_document("doc_gap", "we build state of the art systems")
    idx.add_document("doc_adjacent", "we build state art systems")
    idx.add_document("doc_one_stop", "we build state of art systems")

    res_adj = idx.search('"state art"')
    assert [r.doc_id for r in res_adj] == ["doc_adjacent"]

    res_one = idx.search('"state of art"')
    assert [r.doc_id for r in res_one] == ["doc_one_stop"]

    res_two = idx.search('"state of the art"')
    assert [r.doc_id for r in res_two] == ["doc_gap"]


def test_phrase_with_leading_stopword_matches_correctly():
    idx = SearchIndex()
    idx.add_document("d1", "welcome to the jungle today")
    idx.add_document("d2", "jungle today is green")

    res = idx.search('"the jungle today"')
    assert [r.doc_id for r in res] == ["d1", "d2"]


def test_reindex_existing_document_removes_old_terms_and_positions():
    idx = SearchIndex()
    idx.add_document("doc1", "alpha beta gamma")
    idx.add_document("doc2", "beta delta")

    idx.add_document("doc1", "delta epsilon")

    assert idx.doc_count == 2
    assert idx.search("alpha") == []
    assert [r.doc_id for r in idx.search("beta")] == ["doc2"]
    assert [r.doc_id for r in idx.search('"delta epsilon"')] == ["doc1"]


def test_reindex_updates_tf_and_idf_accurately():
    idx = SearchIndex()
    idx.add_document("d1", "rust python")
    idx.add_document("d2", "rust golang")

    idx.add_document("d1", "python golang")

    results = idx.search("rust")
    assert len(results) == 1
    assert results[0].doc_id == "d2"
    expected_idf = math.log((2 + 1) / (1 + 1)) + 1.0
    expected_score = round((1 / 2) * expected_idf, 6)
    assert results[0].score == expected_score


def test_remove_document_cleans_up_df_for_remaining_docs():
    idx = SearchIndex()
    idx.add_document("d1", "kernel driver")
    idx.add_document("d2", "kernel module")

    assert idx.remove_document("d1") is True
    assert idx.remove_document("d1") is False
    assert idx.doc_count == 1

    res = idx.search("kernel")
    assert len(res) == 1
    expected_idf = math.log((1 + 1) / (1 + 1)) + 1.0
    assert res[0].score == round(0.5 * expected_idf, 6)


def test_tfidf_ranking_order_and_tie_breaking():
    idx = SearchIndex()
    idx.add_document("b_doc", "cloud native")
    idx.add_document("a_doc", "cloud native")
    idx.add_document("c_doc", "cloud cloud native deployment")

    res = idx.search("cloud")
    assert [r.doc_id for r in res] == ["a_doc", "b_doc", "c_doc"]
    assert res[0].score == res[1].score


def test_empty_or_stopword_only_queries_return_empty():
    idx = SearchIndex()
    idx.add_document("d1", "the quick brown fox")
    assert idx.search("") == []
    assert idx.search("the of in") == []
    assert idx.search('"the of"') == []
    assert idx.search("-fox") == []
