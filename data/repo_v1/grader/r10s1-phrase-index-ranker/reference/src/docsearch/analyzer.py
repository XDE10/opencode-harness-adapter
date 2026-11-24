import re
from dataclasses import dataclass, field

STOPWORDS: frozenset[str] = frozenset(
    {"a", "an", "and", "are", "as", "at", "be", "by", "for", "from", "in", "is", "it", "of", "on", "or", "the", "to", "with"}
)

_WORD_RE = re.compile(r"[a-z0-9]+")
_PHRASE_RE = re.compile(r'"([^"]+)"')


@dataclass(frozen=True)
class Token:
    term: str
    position: int


@dataclass
class ParsedQuery:
    required_terms: list[str] = field(default_factory=list)
    excluded_terms: list[str] = field(default_factory=list)
    phrases: list[list[tuple[str, int]]] = field(default_factory=list)


def stem_word(word: str) -> str:
    w = word.lower()
    if len(w) > 4 and w.endswith("ies"):
        return w[:-3] + "y"
    for suffix in ("ing", "ed", "ly", "s"):
        if w.endswith(suffix) and len(w) - len(suffix) >= 3:
            return w[: -len(suffix)]
    return w


def tokenize(text: str) -> list[Token]:
    raw_words = _WORD_RE.findall(text.lower())
    tokens: list[Token] = []
    for pos, word in enumerate(raw_words):
        if word in STOPWORDS:
            continue
        tokens.append(Token(term=stem_word(word), position=pos))
    return tokens


def parse_query(query_text: str) -> ParsedQuery:
    parsed = ParsedQuery()

    for match in _PHRASE_RE.finditer(query_text):
        phrase_str = match.group(1)
        phrase_tokens = tokenize(phrase_str)
        if phrase_tokens:
            parsed.phrases.append([(t.term, t.position) for t in phrase_tokens])

    remainder = _PHRASE_RE.sub(" ", query_text)
    for raw_token in remainder.split():
        is_neg = raw_token.startswith("-") and len(raw_token) > 1
        sub_text = raw_token[1:] if is_neg else raw_token
        for word in _WORD_RE.findall(sub_text.lower()):
            if word in STOPWORDS:
                continue
            stemmed = stem_word(word)
            if is_neg:
                if stemmed not in parsed.excluded_terms:
                    parsed.excluded_terms.append(stemmed)
            else:
                if stemmed not in parsed.required_terms:
                    parsed.required_terms.append(stemmed)

    return parsed
