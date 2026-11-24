# Issue Report: Inverted Index Stale Postings on Upsert/Rollback and Phrase Stopword Offset Drift

## Context
`r10s2idx` is a lightweight in-memory full-text search index supporting tokenization with stopword filtering, transactional document batching (`begin_batch`, `commit_batch`, `rollback_batch`), document upserts, and boolean + exact-phrase query ranking.

## Reported Issues
1. **Phrase matching fails when a query phrase contains stopwords or after stopword stripping**:
   - During indexing, `tokenize_with_positions(text)` strips stopwords (`{"a", "an", "the", "of", "in", "to", "and"}`).
   - According to our specification, token positions recorded in the index must reflect the **original 0-based word position** in the raw tokenized sequence *before* stopwords are filtered out (so `"state of the art"` assigns `"state"` position `0` and `"art"` position `3`).
   - Consistently, when evaluating a phrase query (`match_phrase(index, phrase)`), the phrase parser must also compute each non-stopword query term's relative offset using its **original position in the phrase** (including any stopwords in the phrase), so that `"state of the art"` expects `"art"` at `pos("state") + 3`, and a phrase consisting solely of stopwords returns an empty set of document IDs.
   - Right now, phrase queries with internal stopwords fail to match indexed documents (or vice versa).

2. **Stale postings & document lengths remain after document upsert or batch rollback**:
   - When an already-indexed document ID is updated via `upsert_document(doc_id, text, version=...)`:
     - If `version` is provided and is strictly less than the existing document's `version`, the update must be ignored (`False` returned) as a stale write.
     - Otherwise, all old postings for `doc_id` across the inverted index must be completely removed before indexing the new tokens, and `doc_lengths` / `documents` must reflect the new document. Any terms whose posting maps become empty must be cleaned up (or not treat `doc_id` as matching).
   - When `begin_batch()` is active, `upsert_document` and `delete_document` apply changes tentatively. Calling `rollback_batch()` must restore `documents`, `doc_lengths`, and `postings` to the exact state they had when `begin_batch()` was called, without leaking mutated posting lists or updated lengths from the rolled-back batch.

## Behavioral Specification
- `Tokenizer.tokenize_with_positions(text: str) -> list[tuple[str, int]]`:
  - Extracts lowercase alphanumeric words (`[a-z0-9]+`), stems common suffixes (`"ing"`, `"ed"`, `"s"` when word length > 4, applied once in that priority order), and skips stopwords (`STOPWORDS`).
  - Returns `(stemmed_token, original_word_index)` where `original_word_index` is the 0-based index among all raw `[a-z0-9]+` words in `text` (prior to stopword removal).
- `InvertedIndex`:
  - `upsert_document(doc_id: str, text: str, version: int = 1) -> bool`: Inserts or replaces `doc_id`. Rejects (`returns False`) only if `doc_id` already exists and `version < existing_doc.version`. Otherwise removes prior postings for `doc_id`, indexes the new text, and returns `True`.
  - `delete_document(doc_id: str) -> bool`: Removes `doc_id` and all its postings; returns `True` if it existed, `False` otherwise.
  - `begin_batch()`, `commit_batch()`, `rollback_batch()`: Supports single-level transactional batching. `rollback_batch()` reverts all index structures (`documents`, `doc_lengths`, `postings`) to their pre-batch snapshot.
- `QueryEngine`:
  - `match_phrase(phrase: str) -> set[str]`: Matches documents containing all non-stopword terms of `phrase` at exact relative original word offsets (`pos(term_i) - pos(term_0) == offset_i - offset_0`).
  - `search(must_terms=(), should_terms=(), not_terms=(), phrases=(), top_k=10) -> list[SearchResult]`: Filters candidate docs by all `must_terms`, all `phrases`, and excludes `not_terms`. If neither `must_terms` nor `phrases` are given, candidates are the union of `should_terms` matches. Ranks candidates by TF-IDF-like score over `must_terms + should_terms + phrase_terms`, breaking ties by `doc_id` ascending.
