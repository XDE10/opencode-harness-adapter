import copy

def _unescape(token):
    out = []
    i = 0
    while i < len(token):
        if token[i] != "~": out.append(token[i]); i += 1; continue
        if i + 1 >= len(token) or token[i + 1] not in "01": raise ValueError("bad escape")
        out.append("~" if token[i + 1] == "0" else "/"); i += 2
    return "".join(out)

def _tokens(path):
    if path == "": return []
    if not isinstance(path, str) or not path.startswith("/"): raise ValueError("bad path")
    return [_unescape(part) for part in path.split("/")[1:]]

def _index(token, length, allow_end=False):
    if not token or not token.isdigit() or (len(token) > 1 and token[0] == "0"): raise IndexError("bad index")
    idx = int(token)
    if allow_end:
        if idx < 0: raise IndexError("bad index")
    elif idx >= length: raise IndexError("index out of range")
    return idx

def _parent(doc, tokens):
    cur = doc
    for token in tokens[:-1]:
        if isinstance(cur, dict):
            if token not in cur: raise KeyError(token)
            cur = cur[token]
        elif isinstance(cur, list): cur = cur[_index(token, len(cur))]
        else: raise TypeError("scalar traversal")
    return cur, tokens[-1]

def _get(doc, tokens):
    if not tokens: return copy.deepcopy(doc)
    parent, token = _parent(doc, tokens)
    if isinstance(parent, dict):
        if token not in parent: raise KeyError(token)
        return copy.deepcopy(parent[token])
    if isinstance(parent, list): return copy.deepcopy(parent[_index(token, len(parent))])
    raise TypeError("scalar target")

def _set(doc, tokens, value):
    if not tokens: return copy.deepcopy(value)
    parent, token = _parent(doc, tokens)
    val = copy.deepcopy(value)
    if isinstance(parent, dict): parent[token] = val
    elif isinstance(parent, list):
        if token == "-": parent.append(val)
        else:
            idx = _index(token, len(parent), allow_end=True)
            if idx >= len(parent): parent.append(val)
            else: parent[idx] = val
    else: raise TypeError("scalar target")
    return doc

def _remove(doc, tokens):
    if not tokens: raise ValueError("cannot remove root")
    parent, token = _parent(doc, tokens)
    if isinstance(parent, dict):
        if token not in parent: raise KeyError(token)
        del parent[token]
    elif isinstance(parent, list): del parent[_index(token, len(parent))]
    else: raise TypeError("scalar target")

def run_pointer(doc, ops):
    if not isinstance(ops, list): raise ValueError("ops must be a list")
    current = copy.deepcopy(doc)
    results = []
    for op in ops:
        if not isinstance(op, dict): raise ValueError("op must be a dict")
        name = op.get("op")
        if name not in {"get", "set", "remove"}: raise ValueError("bad op")
        if "path" not in op or not isinstance(op["path"], str): raise ValueError("bad path")
        tokens = _tokens(op["path"])
        if name == "get": results.append(_get(current, tokens))
        elif name == "set":
            if "value" not in op: raise ValueError("missing value")
            current = _set(current, tokens, op["value"])
            results.append(None)
        else:
            _remove(current, tokens)
            results.append(None)
    return {"results": results, "doc": current}
