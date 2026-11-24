def _int(v, positive=False):
    if type(v) is not int or (positive and v < 1): raise ValueError
    return v


def _job(v):
    if not isinstance(v, str) or not v: raise ValueError
    return v


def _head(op):
    if not isinstance(op, dict): raise ValueError
    name = op.get("op")
    if not isinstance(name, str): raise ValueError
    t = _int(op.get("t"))
    if t < 0: raise ValueError
    return name, t


def _active(states, op):
    job = _job(op.get("job"))
    st = states.get(job)
    if st is None or st["state"] != "active": raise ValueError
    return job, st


def run(ops):
    if not isinstance(ops, list): raise ValueError
    states, out = {}, []
    for op in ops:
        name, t = _head(op)
        if name == "submit":
            job = _job(op.get("job"))
            base = _int(op.get("base"), True)
            factor = _int(op.get("factor"), True)
            limit = _int(op.get("max_attempts"), True)
            old = states.get(job)
            if old is not None and old["state"] == "active": raise ValueError
            states[job] = {"state": "active", "due": t, "attempts": 0, "base": base, "factor": factor, "max_attempts": limit}
            out.append("submitted")
        elif name == "run":
            _, st = _active(states, op)
            if t < st["due"]:
                out.append("waiting")
                continue
            st["attempts"] += 1
            if st["attempts"] > st["max_attempts"]:
                st["state"], res = "failed", "failed"
            else:
                st["due"] = t + st["base"] * st["factor"] ** st["attempts"]
                res = "retry"
            out.append(res)
        elif name == "succeed":
            _, st = _active(states, op)
            if t < st["due"]: out.append("waiting")
            else:
                st["state"] = "done"
                out.append("done")
        elif name == "cancel":
            _, st = _active(states, op)
            st["state"] = "cancelled"
            out.append("cancelled")
        elif name == "status":
            job = _job(op.get("job"))
            st = states.get(job)
            if st is None: raise ValueError
            if st["state"] != "active": out.append(st["state"])
            elif t < st["due"]: out.append("waiting")
            else: out.append("ready")
        else:
            raise ValueError
    return out
