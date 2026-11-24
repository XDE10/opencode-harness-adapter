from dataclasses import dataclass
import math
from r10s3pkg.analyzer import ParsedPhrase, TextAnalyzer


@dataclass(frozen=True)
class SearchResult:
    doc_id: str
    score: float


class InvertedIndex:
    def __init__(self, analyzer: TextAnalyzer | None = None) -> None:
        self.analyzer = analyzer or TextAnalyzer()
        self._postings: dict[str, dict[str, list[int]]] = {}
        self._documents: dict[str, str] = {}
        self._doc_count: int = 0

    @property
    def doc_count(self) -> int:
        return self._doc_count

    def add_document(self, doc_id: str, text: str) -> None:
        self._documents[doc_id] = text
        self._doc_count += 1
        for token in self.analyzer.tokenize(text):
            doc_map = self._postings.setdefault(token.term, {})
            doc_map.setdefault(doc_id, []).append(token.position)

    def remove_document(self, doc_id: str) -> bool:
        if doc_id not in self._documents:
            return False
        del self._documents[doc_id]
        self._doc_count -= 1
        empty_terms: list[str] = []
        for term, doc_map in self._postings.items():
            if doc_id in doc_map:
                del doc_map[doc_id]
                if not doc_map:
                    empty_terms.append(term)
        for term in empty_terms:
            del self._postings[term]
        return True

    def _matches_phrase(self, doc_id: str, phrase: ParsedPhrase) -> bool:
        if not phrase.tokens:
            return True
        first_term, first_offset = phrase.tokens[0]
        first_positions = self._postings.get(first_term, {}).get(doc_id, [])
        if not first_positions:
            return False
        for pos in first_positions:
            base_pos = pos - first_offset
            matched_all = True
            for term, rel_offset in phrase.tokens[1:]:
                term_positions = self._postings.get(term, {}).get(doc_id, [])
                if (base_pos + rel_offset) not in term_positions:
                    matched_all = False
                    break
            if matched_all:
                return True
        return False

    def search(self, raw_query: str, top_k: int = 10) -> list[SearchResult]:
        query = self.analyzer.parse_query(raw_query)
        if not query.must_terms and not query.phrases:
            return []

        candidate_docs: set[str] | None = None
        for term in query.must_terms:
            matching = set(self._postings.get(term, {}).keys())
            candidate_docs = matching if candidate_docs is None else (candidate_docs & matching)

        for phrase in query.phrases:
            for term, _ in phrase.tokens:
                matching = set(self._postings.get(term, {}).keys())
                candidate_docs = matching if candidate_docs is None else (candidate_docs & matching)

        if not candidate_docs:
            return []

        for not_term in query.not_terms:
            excluded = set(self._postings.get(not_term, {}).keys())
            candidate_docs -= excluded

        matched_docs = [
            doc_id
            for doc_id in candidate_docs
            if all(self._matches_phrase(doc_id, phrase) for phrase in query.phrases)
        ]

        scoring_terms: list[str] = []
        for t in query.must_terms:
            if t not in scoring_terms:
                scoring_terms.append(t)
        for phrase in query.phrases:
            for t, _ in phrase.tokens:
                if t not in scoring_terms:
                    scoring_terms.append(t)

        results: list[SearchResult] = []
        for doc_id in matched_docs:
            score = 0.0
            for term in scoring_terms:
                doc_map = self._postings.get(term, {})
                df = len(doc_map)
                if df == 0:
                    continue
                tf = len(doc_map.get(doc_id, []))
                idf = math.log(1.0 + (self._doc_count / df))
                score += tf * idf
            results.append(SearchResult(doc_id=doc_id, score=round(score, 6)))

        results.sort(key=lambda r: (-r.score, r.doc_id))
        return results[:top_k]
