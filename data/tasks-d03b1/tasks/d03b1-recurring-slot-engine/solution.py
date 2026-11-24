def _generate_clipped(start, duration, period, count, horizon):
    occ = {}
    for k in range(count):
        s = start + k * period
        if s >= horizon:
            break
        e = min(s + duration, horizon)
        occ[k] = (s, e)
    return occ


def _overlaps(a_s, a_e, b_s, b_e):
    return max(a_s, b_s) < min(a_e, b_e)


def run_recurring_schedule(horizon, ops):
    if horizon < 1:
        raise ValueError("horizon must be >= 1")

    series_map = {}
    skipped = {}
    results = []

    for item in ops:
        kind = item.get("op")
        if kind == "add_series":
            sid = item["id"]
            start = item["start"]
            duration = item["duration"]
            period = item["period"]
            count = item["count"]
            if (
                sid in series_map
                or start < 0
                or duration < 1
                or period <= duration
                or count < 1
            ):
                raise ValueError("Invalid add_series parameters")

            occ = _generate_clipped(start, duration, period, count, horizon)
            if not occ:
                raise ValueError("No occurrences in horizon")

            conflict = False
            for s, e in occ.values():
                for other_id, other_info in series_map.items():
                    other_skips = skipped.get(other_id, set())
                    for k, (os, oe) in other_info["occ"].items():
                        if k in other_skips:
                            continue
                        if _overlaps(s, e, os, oe):
                            conflict = True
                            break
                    if conflict:
                        break
                if conflict:
                    break

            if conflict:
                results.append(False)
            else:
                series_map[sid] = {"count": count, "occ": occ}
                results.append(True)

        elif kind == "skip_occurrence":
            sid = item["id"]
            idx = item["index"]
            if sid not in series_map:
                raise ValueError("Unknown series")
            info = series_map[sid]
            if idx < 0 or idx >= info["count"]:
                raise ValueError("Index out of range")
            skips = skipped.setdefault(sid, set())
            if idx not in info["occ"] or idx in skips:
                results.append(False)
            else:
                skips.add(idx)
                results.append(True)

        elif kind == "remove_series":
            sid = item["id"]
            if sid in series_map:
                del series_map[sid]
                results.append(True)
            else:
                results.append(False)

        elif kind == "query_window":
            w_start = item["start"]
            w_end = item["end"]
            if w_start < 0 or w_start >= w_end or w_end > horizon:
                raise ValueError("Invalid query window")
            found = []
            for sid, info in series_map.items():
                skips = skipped.get(sid, set())
                for k, (os, oe) in info["occ"].items():
                    if k in skips:
                        continue
                    if _overlaps(w_start, w_end, os, oe):
                        found.append([max(w_start, os), min(w_end, oe), sid])
            found.sort()
            results.append(found)

        else:
            raise ValueError(f"Unknown op: {kind}")

    return results
