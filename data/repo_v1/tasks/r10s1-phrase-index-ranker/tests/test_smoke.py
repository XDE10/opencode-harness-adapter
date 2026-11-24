from docsearch import SearchIndex, stem_word, tokenize


def test_stem_and_tokenize_basic():
    tokens = tokenize("Running fast systems")
    assert [t.term for t in tokens] == ["runn", "fast", "system"]
    assert stem_word("queries") == "query"


def test_basic_boolean_search():
    idx = SearchIndex()
    idx.add_document("d1", "distributed database engine")
    idx.add_document("d2", "distributed cache engine")
    idx.add_document("d3", "local sqlite database")

    res = idx.search("distributed -cache")
    assert [r.doc_id for r in res] == ["d1"]


def test_simple_adjacent_phrase():
    idx = SearchIndex()
    idx.add_document("d1", "fast full text search engine")
    idx.add_document("d2", "search text fast in engine")

    res = idx.search('"text search"')
    assert [r.doc_id for r in res] == ["d1"]
