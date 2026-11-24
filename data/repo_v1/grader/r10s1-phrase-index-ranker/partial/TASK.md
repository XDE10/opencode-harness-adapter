# Issue Report: Phrase Matching with Stopwords and Re-indexed Document Statistics

## Context
`docsearch` is an in-memory full-text search engine that tokenizes and stems documents, builds a positional inverted index, and evaluates boolean (`AND`, `-exclude`) + exact phrase (`"..."`) queries with TF-IDF ranking.

## Reported Symptoms
1. **Phrase queries across stopwords or punctuation fail or falsely match**:
   When indexing text, stopwords (e.g., `"the"`, `"of"`, `"in"`, `"a"`, `"to"`, `"and"`) are excluded from the inverted index to save space, while still occupying their original token positions in the document stream. However, when a user searches for a phrase containing a stopword (such as `"state of art"` against `"state of the art"` or `"state of art"`) or when a phrase spans across removed stopwords, phrase positional matching behaves inconsistently:
   - In `analyzer.py`, `tokenize()` increments positional indices only for non-stopwords instead of preserving the actual token stream position (or conversely, `parse_query` strips stopwords from phrases without accounting for their positional gap).
   - Specifically, the required specification for token positions is:
     - Every raw alphanumeric token extracted from a document (0-based order of appearance in the document) has a stream position `0, 1, 2, ...` **before** stopword filtering. Stopwords are dropped from the returned `Token` list, so the remaining `Token` objects retain their true stream positions (e.g., in `"state of art"`, `"state"` is at `pos=0`, `"of"` is a stopword at `pos=1`, and `"art"` is at `pos=2`).
     - In `parse_query()`, quoted phrases `"..."` must also be tokenized using `keep_positions=True` (preserving relative positional offsets between kept terms in the phrase, e.g. `"state of art"` produces phrase terms `[("state", 0), ("art", 2)]`). When matching a phrase in `SearchIndex._match_phrase(doc_id, phrase_terms)`, a document matches if there exists a base position `p` such that for every `(term, offset)` in `phrase_terms`, `p + offset` is in that term's positions for `doc_id`. (If all tokens in a quoted phrase are stopwords, it contributes no phrase constraint).

2. **Re-indexing (updating) or deleting an existing `doc_id` corrupts corpus statistics and stale postings**:
   `SearchIndex.add_document(doc_id, text)` allows updating an existing document by passing the same `doc_id`. Currently:
   - Re-adding an existing `doc_id` leaves stale posting entries for terms that were present in the old version of the document but not in the new version, or appends duplicate positions instead of replacing the document cleanly.
   - `doc_lengths` and IDF document frequency (`df`) calculations become skewed after updating or removing a document because stale postings remain in the inverted index.

## Behavioral Specification
- **Tokenization & Stemming (`docsearch.analyzer`)**:
  - Extract lowercase alphanumeric words matching `[a-z0-9]+`.
  - Raw tokens are assigned 0-based positions `0, 1, 2, ...` in order of appearance.
  - Stopwords (`STOPWORDS`) are filtered out.
  - Non-stopwords are stemmed with `stem_word(word)` (strips suffix `"ing"`, `"ed"`, `"ly"`, `"s"` when the remaining stem is at least 3 characters long; if a word ends with `"ies"` and length > 4, converts `"ies"` -> `"y"`).
  - `tokenize(text)` returns `list[Token(term, position)]` where `position` is the token's 0-based index in the raw token stream prior to stopword removal.
- **Query Parsing (`docsearch.analyzer.parse_query`)**:
  - Extracts double-quoted phrases `"..."`, negative terms `-word`, and required positive terms `word`.
  - Each quoted phrase is stored as `list[tuple[str, int]]` representing `[(stemmed_term, relative_offset), ...]` using the raw token stream offsets within that phrase (skipping stopwords while preserving their offset gap; if a phrase has only stopwords, it is ignored).
  - Standalone positive and negative terms are stemmed; stopwords are ignored.
- **Indexing & Ranking (`docsearch.index.SearchIndex`)**:
  - `add_document(doc_id, text)`: If `doc_id` already exists, all of its previous postings and metadata must be completely replaced by the new document's tokens. `doc_lengths[doc_id]` stores the number of indexed (non-stopword) tokens in the document.
  - `remove_document(doc_id)`: Removes the document and cleans up empty term posting lists. Returns `True` if removed, `False` if `doc_id` was not present.
  - `search(query_text, top_k=10)`:
    - Candidate documents must contain **all** `required_terms`, **all** `phrases` (matching relative positional offsets), and **none** of `excluded_terms`.
    - If a query has no required terms and no non-empty phrases, return `[]`.
    - Ranking score for each matching document sums over all unique query terms (union of `required_terms` and terms appearing in `phrases`):
      $$\text{score}(d) = \sum_{t \in Q} \left(\frac{\text{tf}(t, d)}{\text{doc\_length}(d)}\right) \times \left(\ln\left(\frac{N + 1}{\text{df}(t) + 1}\right) + 1.0\right)$$
      where $N$ is total currently indexed documents, $\text{df}(t)$ is number of currently indexed documents containing $t$, and $\text{tf}(t, d)$ is the count of occurrences of $t$ in document $d$.
    - Results are returned as `list[SearchResult(doc_id, score)]` (score rounded to 6 decimal places), sorted by `(-score, doc_id)`.
