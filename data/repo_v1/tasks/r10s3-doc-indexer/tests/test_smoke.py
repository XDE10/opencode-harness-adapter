from r10s3pkg import InvertedIndex, TextAnalyzer


def test_basic_boolean_search():
    idx = InvertedIndex()
    idx.add_document("doc1", "Python search engine with inverted index")
    idx.add_document("doc2", "Python web service with database")

    results = idx.search("python -database")
    assert [r.doc_id for r in results] == ["doc1"]


def test_adjacent_phrase_search():
    idx = InvertedIndex()
    idx.add_document("doc1", "fast inverted index builder")
    idx.add_document("doc2", "index fast builder inverted")

    results = idx.search('"inverted index"')
    assert [r.doc_id for r in results] == ["doc1"]


def test_analyzer_stemming():
    analyzer = TextAnalyzer()
    tokens = analyzer.tokenize("indexing searches running")
    assert [t.term for t in tokens] == ["index", "search", "run"]
