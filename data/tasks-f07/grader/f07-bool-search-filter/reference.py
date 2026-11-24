def _tokenize(query: str):
    tokens = []
    i = 0
    n = len(query)
    while i < n:
        if query[i].isspace():
            i += 1
            continue
        if query[i] in "()":
            tokens.append(("PAREN", query[i]))
            i += 1
            continue
        buf = []
        while i < n and not query[i].isspace() and query[i] not in "()":
            if query[i] in ("'", '"'):
                q = query[i]
                i += 1
                start = i
                while i < n and query[i] != q:
                    i += 1
                if i >= n:
                    raise ValueError("unclosed quote")
                buf.append(query[start:i])
                i += 1
            else:
                buf.append(query[i])
                i += 1
        word = "".join(buf)
        if word in ("AND", "OR", "NOT"):
            tokens.append(("KW", word))
        else:
            tokens.append(("PRED", word))
    return tokens


def _match_pred(rec: dict, pred: str) -> bool:
    if pred.startswith("has:"):
        field = pred[4:]
        if not field:
            raise ValueError("empty field")
        return rec.get(field) is not None
    for op in (">=", "<=", "=", ">", "<", "~", ":"):
        if op in pred:
            field, rhs = pred.split(op, 1)
            if not field or rhs == "":
                raise ValueError("invalid predicate")
            if field not in rec or rec[field] is None:
                return False
            val = rec[field]
            if op in (">=", "<=", "=", ">", "<"):
                try:
                    target = int(rhs)
                except ValueError as exc:
                    raise ValueError("invalid integer") from exc
                if isinstance(val, bool) or not isinstance(val, int):
                    return False
                if op == "=": return val == target
                if op == ">=": return val >= target
                if op == "<=": return val <= target
                return val > target if op == ">" else val < target
            if op == "~":
                needle = rhs.lower()
                if isinstance(val, str):
                    return needle in val.lower()
                if isinstance(val, list):
                    return any(isinstance(x, str) and needle in x.lower() for x in val)
                return False
            if isinstance(val, list):
                return any(
                    (str(x).lower() if isinstance(x, bool) else str(x)) == rhs
                    for x in val if isinstance(x, (str, int))
                )
            if isinstance(val, bool):
                return rhs.lower() in ("true", "false") and val == (rhs.lower() == "true")
            if isinstance(val, int):
                try:
                    return val == int(rhs)
                except ValueError:
                    return False
            return isinstance(val, str) and val == rhs
    raise ValueError(f"invalid predicate: {pred}")


def filter_records(records, query):
    if not isinstance(query, str) or not query.strip():
        raise ValueError("empty query")
    tokens = _tokenize(query)
    pos = 0

    def peek():
        return tokens[pos] if pos < len(tokens) else None

    def parse_or():
        node = parse_and()
        while peek() == ("KW", "OR"):
            nonlocal pos
            pos += 1
            node = ("OR", node, parse_and())
        return node

    def parse_and():
        node = parse_not()
        while peek() == ("KW", "AND"):
            nonlocal pos
            pos += 1
            node = ("AND", node, parse_not())
        return node

    def parse_not():
        nonlocal pos
        if peek() == ("KW", "NOT"):
            pos += 1
            return ("NOT", parse_not())
        return parse_atom()

    def parse_atom():
        nonlocal pos
        tok = peek()
        if tok is None:
            raise ValueError("unexpected end of query")
        if tok == ("PAREN", "("):
            pos += 1
            node = parse_or()
            if peek() != ("PAREN", ")"):
                raise ValueError("unmatched parenthesis")
            pos += 1
            return node
        if tok[0] == "PRED":
            pos += 1
            return ("PRED", tok[1])
        raise ValueError(f"unexpected token: {tok[1]}")

    ast = parse_or()
    if pos != len(tokens):
        raise ValueError("trailing tokens")

    def eval_ast(node, rec):
        tag = node[0]
        if tag == "PRED":
            return _match_pred(rec, node[1])
        if tag == "NOT":
            return not eval_ast(node[1], rec)
        if tag == "AND":
            return eval_ast(node[1], rec) and eval_ast(node[2], rec)
        return eval_ast(node[1], rec) or eval_ast(node[2], rec)

    return [rec["id"] for rec in records if eval_ast(ast, rec)]
