from dataclasses import dataclass
import math
from r10s2idx.indexer import InvertedIndex


@dataclass(frozen=True)
class SearchResult:
    doc_id: str
    score: float


class QueryEngine:
    def __init__(self, index: InvertedIndex) -> None:
        self.index = index

    def match_phrase(self, phrase: str) -> set[str]:
        tokens_with_pos = self.index.tokenizer.tokenize_with_positions(phrase)
        if not tokens_with_pos:
            return set()

        first_term, first_offset = tokens_with_pos[0]
        candidate_docs = set(self.index.postings.get(first_term, {}).keys())
        if len(tokens_with_pos) == 1:
            return candidate_docs

        matched: set[str] = set()
        for doc_id in candidate_docs:
            anchor_positions = self.index.postings.get(first_term, {}).get(doc_id, [])
            for anchor_pos in anchor_positions:
                all_found = True
                for term, offset in tokens_with_pos[1:]:
                    expected_pos = anchor_pos + (offset - first_offset)
                    term_positions = self.index.postings.get(term, {}).get(doc_id, [])
                    if expected_pos not in term_positions:
                        all_found = False
                        break
                if all_found:
                    matched.add(doc_id)
                    break
        return matched

    def search(
        self,
        must_terms: tuple[str, ...] | list[str] = (),
        should_terms: tuple[str, ...] | list[str] = (),
        not_terms: tuple[str, ...] | list[str] = (),
        phrases: tuple[str, ...] | list[str] = (),
        top_k: int = 10,
    ) -> list[SearchResult]:
        must_norm = [t for word in must_terms for t in self.index.tokenizer.tokenize_terms(word)]
        should_norm = [t for word in should_terms for t in self.index.tokenizer.tokenize_terms(word)]
        not_norm = [t for word in not_terms for t in self.index.tokenizer.tokenize_terms(word)]

        candidates: set[str] | None = None
        for term in must_norm:
            term_docs = set(self.index.postings.get(term, {}).keys())
            candidates = term_docs if candidates is None else (candidates & term_docs)

        for phrase in phrases:
            phrase_docs = self.match_phrase(phrase)
            candidates = phrase_docs if candidates is None else (candidates & phrase_docs)

        if candidates is None:
            candidates = set()
            for term in should_norm:
                candidates |= set(self.index.postings.get(term, {}).keys())

        for term in not_norm:
            candidates -= set(self.index.postings.get(term, {}).keys())

        if not candidates:
            return []

        scoring_terms: list[str] = list(dict.fromkeys(
            must_norm
            + should_norm
            + [t for p in phrases for t in self.index.tokenizer.tokenize_terms(p)]
        ))

        total_docs = max(1, len(self.index.documents))
        results: list[SearchResult] = []
        for doc_id in candidates:
            doc_len = max(1, self.index.doc_lengths.get(doc_id, 1))
            score = 0.0
            for term in scoring_terms:
                term_docs = self.index.postings.get(term, {})
                tf = len(term_docs.get(doc_id, [])) / doc_len
                if tf > 0:
                    df = len(term_docs)
                    idf = 1.0 + math.log((total_docs + 1) / (df + 1))
                    score += tf * idf
            results.append(SearchResult(doc_id=doc_id, score=round(score, 6)))

        results.sort(key=lambda r: (-r.score, r.doc_id))
        return results[:top_k]
