# Issue Report: Phrase Query Stopword Gaps and Stale Postings on Document Re-indexing

## Summary
Users of `r10s3pkg` (our in-memory full-text search index) have reported two regressions when running phrase queries and updating existing documents:

1. **Phrase queries across stopwords fail to match**: When a document contains a phrase with stopwords in between (e.g., `"state of the art"`), searching for `"state of the art"` fails to match the document even though both the document analyzer and query parser use the same `TextAnalyzer`.
2. **Re-indexing an existing `doc_id` corrupts search results and scoring**: Calling `InvertedIndex.add_document(doc_id, text)` with a `doc_id` that already exists in the index leaves stale term postings from the previous version of the document and throws off corpus statistics (`doc_count` / IDF scoring).

## Behavioral Specification

### 1. Tokenization, Stemming, and Token Positions (`r10s3pkg.analyzer`)
- `TextAnalyzer` extracts lowercase alphanumeric word tokens (`[a-z0-9]+`).
- **Position tracking (`tokenize`)**:
  - Every raw word token in the input text is assigned a 0-based sequential integer position (`0, 1, 2, ...`) **before** stopword filtering.
  - Stopwords (tokens present in `stopwords` set, after lowercasing) are excluded from the returned `Token` list, **preserving the original token positions** of the remaining words. For example, in `"state of the art"` (where `"of"` and `"the"` are stopwords), `"state"` has position `0` and `"art"` has position `3`.
  - Non-stopword tokens are stemmed via `stem(word)`.
- **Query parsing (`parse_query`)**:
  - Extracts double-quoted phrases (`"..."`), negated terms (`-word`), and required positive terms (`word`).
  - For each double-quoted phrase, `parse_query` must analyze the phrase text with `tokenize()` and record the relative position offsets between the remaining non-stopword tokens (or their relative `(term, offset_from_first_token)` pairs) so that phrases containing stopwords require the exact same positional gap in indexed documents.
  - If a quoted phrase contains only stopwords (or no valid tokens), it is ignored.
  - Single positive terms and negated (`-term`) tokens are lowercased, ignored if they are stopwords, and stemmed.

### 2. Stateful Indexing and Re-indexing (`r10s3pkg.indexer`)
- `InvertedIndex.add_document(doc_id: str, text: str) -> None`:
  - If `doc_id` was already indexed, all of its previous postings and document metadata must be cleanly replaced before indexing the new text (equivalent to removing the old version first).
  - `doc_count` must reflect the number of currently active unique documents in the index.
  - If `remove_document(doc_id: str) -> bool` is called:
    - Returns `True` if `doc_id` existed and was removed, `False` otherwise.
    - Removes the document's postings from all inverted lists and deletes any term keys whose posting dicts become empty.

### 3. Query Execution & Ranking (`r10s3pkg.indexer`)
- `InvertedIndex.search(raw_query: str, top_k: int = 10) -> list[SearchResult]`:
  - If the parsed query has no positive terms and no phrases, returns `[]`.
  - Candidate documents must match **all** positive terms (`ParsedQuery.must_terms`), **all** phrases (`ParsedQuery.phrases`), and **none** of the negated terms (`ParsedQuery.not_terms`).
  - A phrase matches a document if there exists a base position `p0` for the first token in the phrase such that every token `(term_i, rel_offset_i)` in the phrase occurs at position `p0 + rel_offset_i` in that document.
  - Scoring:
    - For each unique matched term across `must_terms` and tokens in `phrases` (deduplicated in order of appearance, or set of distinct query terms):
      $$\text{tf}(t, d) = \text{count of term } t \text{ in document } d$$
      $$\text{idf}(t) = \ln\left(1 + \frac{N}{\text{df}(t)}\right)$$
      where $N$ is the active `doc_count` and $\text{df}(t)$ is the number of active documents containing term $t$.
      $$\text{score}(d) = \sum_{t \in Q_{\text{distinct}}} \text{tf}(t, d) \times \text{idf}(t)$$
  - Results are sorted by `score` descending (rounded to 6 decimal places in `SearchResult.score`), with ties broken by `doc_id` ascending.
