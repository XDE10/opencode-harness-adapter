from dataclasses import dataclass, field
import re

DEFAULT_STOPWORDS = frozenset(
    {"a", "an", "and", "are", "as", "at", "be", "by", "for", "from", "in", "is", "it", "of", "on", "or", " the", "the", "to", "with"}
)

_WORD_RE = re.compile(r"[a-z0-9]+")
_QUERY_TOKEN_RE = re.compile(r'"([^"]*)"|(-?[a-zA-Z0-9]+)')


@dataclass(frozen=True)
class Token:
    term: str
    position: int


@dataclass(frozen=True)
class ParsedPhrase:
    tokens: tuple[tuple[str, int], ...]


@dataclass
class ParsedQuery:
    must_terms: list[str] = field(default_factory=list)
    not_terms: list[str] = field(default_factory=list)
    phrases: list[ParsedPhrase] = field(default_factory=list)


class TextAnalyzer:
    def __init__(self, stopwords: set[str] | frozenset[str] | None = None) -> None:
        self.stopwords = frozenset(w.strip().lower() for w in (stopwords if stopwords is not None else DEFAULT_STOPWORDS))

    def stem(self, word: str) -> str:
        w = word.lower()
        if len(w) > 5 and w.endswith("ing"):
            w = w[:-3]
            if len(w) >= 2 and w[-1] == w[-2]:
                w = w[:-1]
            return w
        if len(w) > 4 and w.endswith("ed"):
            w = w[:-2]
            if len(w) >= 2 and w[-1] == w[-2]:
                w = w[:-1]
            return w
        if len(w) > 4 and w.endswith("es"):
            return w[:-2]
        if len(w) > 3 and w.endswith("s") and not w.endswith("ss"):
            return w[:-1]
        return w

    def tokenize(self, text: str) -> list[Token]:
        raw_words = _WORD_RE.findall(text.lower())
        tokens: list[Token] = []
        for pos, word in enumerate(raw_words):
            if word in self.stopwords:
                continue
            tokens.append(Token(term=self.stem(word), position=pos))
        return tokens

    def parse_query(self, raw_query: str) -> ParsedQuery:
        parsed = ParsedQuery()
        for match in _QUERY_TOKEN_RE.finditer(raw_query):
            phrase_body, single_token = match.groups()
            if phrase_body is not None:
                phrase_tokens = self.tokenize(phrase_body)
                if phrase_tokens:
                    base_pos = phrase_tokens[0].position
                    rel = tuple((t.term, t.position - base_pos) for t in phrase_tokens)
                    parsed.phrases.append(ParsedPhrase(tokens=rel))
            elif single_token is not None:
                negated = single_token.startswith("-")
                raw_word = single_token[1:].lower() if negated else single_token.lower()
                if not raw_word or raw_word in self.stopwords:
                    continue
                stemmed = self.stem(raw_word)
                if negated:
                    if stemmed not in parsed.not_terms:
                        parsed.not_terms.append(stemmed)
                else:
                    if stemmed not in parsed.must_terms:
                        parsed.must_terms.append(stemmed)
        return parsed
