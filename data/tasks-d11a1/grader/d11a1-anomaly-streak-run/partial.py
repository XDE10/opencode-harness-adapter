THRESHOLD = 10
GAP = 5
NEED = 2


def _new_state():
    return {"prev": None, "last_t": None, "streak": 0, "emitted": False}


def _status(st):
    if st is None:
        return {"streak": 0, "emitted": False, "prev": None}
    return {"streak": st["streak"], "emitted": st["emitted"], "prev": st["prev"]}


def _observe(states, op, out):
    metric = op["metric"]
    t = op["t"]
    value = op["value"]
    st = states.get(metric)
    if st is None:
        st = _new_state()
        states[metric] = st
    if st["prev"] is None or st["last_t"] is None or t - st["last_t"] > GAP:
        st["streak"] = 0
        st["emitted"] = False
        st["prev"] = value
        st["last_t"] = t
        out.append(None)
        return
    if abs(value - st["prev"]) > THRESHOLD:
        st["streak"] += 1
        if st["streak"] >= NEED and not st["emitted"]:
            out.append({"metric": metric, "t": t, "streak": st["streak"]})
            st["emitted"] = True
        else:
            out.append(None)
    else:
        st["streak"] = 0
        out.append(None)
    st["prev"] = value
    st["last_t"] = t


def _reset(states, op, out):
    states.pop(op["metric"], None)
    out.append(None)


def run(ops):
    states = {}
    out = []
    for op in ops:
        kind = op["op"]
        if kind == "observe":
            _observe(states, op, out)
        elif kind == "reset":
            _reset(states, op, out)
        elif kind == "status":
            out.append(_status(states.get(op["metric"])))
        else:
            raise ValueError("unknown op")
    return out
