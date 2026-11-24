import re

WORD_RE = re.compile(r"[a-z0-9]+")

STOPWORDS: frozenset[str] = frozenset({
    "a", "an", "the", "of", "in", "to", "and",
})


class Tokenizer:
    def __init__(self, stopwords: frozenset[str] = STOPWORDS) -> None:
        self.stopwords = stopwords

    def stem(self, word: str) -> str:
        if len(word) <= 4:
            return word
        for suffix in ("ing", "ed", "s"):
            if word.endswith(suffix) and len(word) - len(suffix) >= 3:
                return word[: -len(suffix)]
        return word

    def extract_raw_words(self, text: str) -> list[str]:
        return WORD_RE.findall(text.lower())

    def tokenize_with_positions(self, text: str) -> list[tuple[str, int]]:
        raw_words = self.extract_raw_words(text)
        tokens: list[tuple[str, int]] = []
        filtered = [w for w in raw_words if w not in self.stopwords]
        for idx, word in enumerate(filtered):
            tokens.append((self.stem(word), idx))
        return tokens

    def tokenize_terms(self, text: str) -> list[str]:
        return [term for term, _ in self.tokenize_with_positions(text)]
