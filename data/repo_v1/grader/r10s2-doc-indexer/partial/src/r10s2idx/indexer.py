from dataclasses import dataclass
from r10s2idx.tokenizer import Tokenizer


@dataclass(frozen=True)
class DocumentRecord:
    doc_id: str
    text: str
    version: int


class InvertedIndex:
    def __init__(self, tokenizer: Tokenizer | None = None) -> None:
        self.tokenizer = tokenizer or Tokenizer()
        self.documents: dict[str, DocumentRecord] = {}
        self.doc_lengths: dict[str, int] = {}
        self.postings: dict[str, dict[str, list[int]]] = {}
        self._snapshot: tuple[
            dict[str, DocumentRecord],
            dict[str, int],
            dict[str, dict[str, list[int]]],
        ] | None = None

    def begin_batch(self) -> None:
        if self._snapshot is not None:
            raise RuntimeError("Batch already in progress")
        self._snapshot = (
            dict(self.documents),
            dict(self.doc_lengths),
            dict(self.postings),
        )

    def commit_batch(self) -> None:
        if self._snapshot is None:
            raise RuntimeError("No active batch")
        self._snapshot = None

    def rollback_batch(self) -> None:
        if self._snapshot is None:
            raise RuntimeError("No active batch")
        self.documents, self.doc_lengths, self.postings = self._snapshot
        self._snapshot = None

    def upsert_document(self, doc_id: str, text: str, version: int = 1) -> bool:
        existing = self.documents.get(doc_id)
        if existing is not None and version < existing.version:
            return False

        tokens_with_pos = self.tokenizer.tokenize_with_positions(text)
        self.documents[doc_id] = DocumentRecord(doc_id=doc_id, text=text, version=version)
        self.doc_lengths[doc_id] = len(tokens_with_pos)

        for term, pos in tokens_with_pos:
            term_postings = self.postings.setdefault(term, {})
            doc_positions = term_postings.setdefault(doc_id, [])
            doc_positions.append(pos)
        return True

    def delete_document(self, doc_id: str) -> bool:
        if doc_id not in self.documents:
            return False
        del self.documents[doc_id]
        self.doc_lengths.pop(doc_id, None)
        self._remove_postings_for_doc(doc_id)
        return True

    def _remove_postings_for_doc(self, doc_id: str) -> None:
        empty_terms: list[str] = []
        for term, doc_map in self.postings.items():
            if doc_id in doc_map:
                del doc_map[doc_id]
                if not doc_map:
                    empty_terms.append(term)
        for term in empty_terms:
            del self.postings[term]

    def term_positions(self, term: str, doc_id: str) -> list[int]:
        stemmed = self.tokenizer.stem(term.lower())
        return list(self.postings.get(stemmed, {}).get(doc_id, []))

    def docs_for_term(self, term: str) -> set[str]:
        stemmed = self.tokenizer.stem(term.lower())
        return set(self.postings.get(stemmed, {}).keys())
