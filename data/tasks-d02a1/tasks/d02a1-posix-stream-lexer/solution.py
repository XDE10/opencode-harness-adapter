class PosixStreamLexer:
    def __init__(self):
        self.reset()

    def reset(self):
        self.mode = "normal"
        self.buf = []
        self.has_token = False
        self.escaping = False
        self.in_comment = False

    def feed(self, chunk: str) -> list[str]:
        emitted = []
        for ch in chunk:
            if self.in_comment:
                if ch == "\n":
                    self.in_comment = False
                continue

            if self.mode == "single":
                if ch == "'":
                    self.mode = "normal"
                else:
                    self.buf.append(ch)
                continue

            if self.mode == "double":
                if self.escaping:
                    self.escaping = False
                    if ch == "\n":
                        continue
                    self.buf.append(ch)
                    continue
                if ch == "\\":
                    self.escaping = True
                    continue
                if ch == '"':
                    self.mode = "normal"
                    continue
                self.buf.append(ch)
                continue

            if self.escaping:
                self.escaping = False
                if ch == "\n":
                    continue
                self.has_token = True
                self.buf.append(ch)
                continue

            if ch == "\\":
                self.escaping = True
                continue
            if ch == "'":
                self.has_token = True
                self.mode = "single"
                continue
            if ch == '"':
                self.has_token = True
                self.mode = "double"
                continue
            if ch == "#":
                if self.buf:
                    self. token_ finish(emitted)
                self.in_comment = True
                continue
            if ch in (" ", "\t", "\n"):
                if self.buf:
                    self. token_ finish(emitted)
                continue

            self.has_token = True
            self.buf.append(ch)
        return emitted

    def token_finish(self, emitted: list[str]):
        emitted.append("".join(self.buf))
        self.buf.clear()
        self.has_token = False

    def flush(self) -> list[str]:
        if self.mode != "normal" or self.escaping:
            self.reset()
            raise ValueError("Incomplete quote or escape at flush")
        out = []
        if self.buf:
            self.token_finish(out)
        self.reset()
        return out


def run_lexer(ops: list[dict]) -> list:
    lexer = PosixStreamLexer()
    results = []
    for item in ops:
        op = item.get("op")
        if op == "feed":
            results.append(lexer.feed(item["chunk"]))
        elif op == "flush":
            results.append(lexer.flush())
        elif op == "reset":
            lexer.reset()
            results.append(None)
        else:
            raise ValueError(f"Unknown op: {op}")
    return results
