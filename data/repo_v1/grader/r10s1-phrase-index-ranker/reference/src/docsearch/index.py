import math
from dataclasses import dataclass
from docsearch.analyzer import parse_query, tokenize


@dataclass(frozen=True)
class SearchResult:
    doc_id: str
    score: float


class SearchIndex:
    def __init__(self) -> None:
        self._postings: dict[str, dict[str, list[int]]] = {}
        self._doc_lengths: dict[str, int] = {}

    @property
    def doc_count(self) -> int:
        return len(self._doc_lengths)

    def add_document(self, doc_id: str, text: str) -> None:
        if doc_id in self._doc_lengths:
            self.remove_document(doc_id)
        tokens = tokenize(text)
        self._doc_lengths[doc_id] = len(tokens)
        for token in tokens:
            term_postings = self._postings.setdefault(token.term, {})
            term_postings.setdefault(doc_id, []).append(token.position)

    def remove_document(self, doc_id: str) -> bool:
        if doc_id not in self._doc_lengths:
            return False
        del self._doc_lengths[doc_id]
        for term in list(self._postings.keys()):
            self._postings[term].pop(doc_id, None)
            if not self._postings[term]:
                del self._postings[term]
        return True

    def _match_phrase(self, doc_id: str, phrase: list[tuple[str, int]]) -> bool:
        if not phrase:
            return True
        first_term, first_offset = phrase[0]
        first_positions = self._postings.get(first_term, {}).get(doc_id, [])
        if not first_positions:
            return False

        for pos in first_positions:
            base = pos - first_offset
            matched = True
            for term, offset in phrase[1:]:
                term_positions = self._postings.get(term, {}).get(doc_id, [])
                if (base + offset) not in term_positions:
                    matched = False
                    break
            if matched:
                return True
        return False

    def search(self, query_text: str, top_k: int = 10) -> list[SearchResult]:
        parsed = parse_query(query_text)
        if not parsed.required_terms and not parsed.phrases:
            return []

        candidates: set[str] | None = None

        for term in parsed.required_terms:
            term_docs = set(self._postings.get(term, {}).keys())
            candidates = term_docs if candidates is None else (candidates & term_docs)

        for phrase in parsed.phrases:
            for term, _ in phrase:
                term_docs = set(self._postings.get(term, {}).keys())
                candidates = term_docs if candidates is None else (candidates & term_docs)

        if not candidates:
            return []

        for neg_term in parsed.excluded_terms:
            candidates -= set(self._postings.get(neg_term, {}).keys())

        matched_docs = [
            doc_id
            for doc_id in candidates
            if all(self._match_phrase(doc_id, phrase) for phrase in parsed.phrases)
        ]

        scoring_terms: list[str] = list(parsed.required_terms)
        for phrase in parsed.phrases:
            for term, _ in phrase:
                if term not in scoring_terms:
                    scoring_terms.append(term)

        total_docs = self.doc_count
        results: list[SearchResult] = []
        for doc_id in matched_docs:
            doc_len = self._doc_lengths[doc_id]
            if doc_len == 0:
                continue
            score = 0.0
            for term in scoring_terms:
                term_postings = self._postings.get(term, {})
                df = len(term_postings)
                tf = len(term_postings.get(doc_id, []))
                idf = math.log((total_docs + 1) / (df + 1)) + 1.0
                score += (tf / doc_len) * idf
            results.append(SearchResult(doc_id=doc_id, score=round(score, 6)))

        results.sort(key=lambda r: (-r.score, r.doc_id))
        return results[:top_k]
