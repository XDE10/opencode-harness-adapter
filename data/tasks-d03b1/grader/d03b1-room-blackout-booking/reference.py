def _overlaps(a_start, a_end, b_start, b_end):
    return max(a_start, b_start) < min(a_end, b_end)


def _subtract_intervals(base_start, base_end, blocked):
    free = [[base_start, base_end]]
    for b_start, b_end in sorted(blocked):
        next_free = []
        for f_start, f_end in free:
            if b_end <= f_start or b_start >= f_end:
                next_free.append([f_start, f_end])
            else:
                if f_start < b_start:
                    next_free.append([f_start, b_start])
                if b_end < f_end:
                    next_free.append([b_end, f_end])
        free = next_free
    return free


def run_bookings(num_rooms, ops):
    if num_rooms < 1:
        raise ValueError("num_rooms must be >= 1")

    bookings = {}
    blackouts = {r: [] for r in range(num_rooms)}
    results = []

    for item in ops:
        kind = item.get("op")
        if kind == "book":
            bid = item["id"]
            start, end = item["start"], item["end"]
            pref = item.get("room")
            if start >= end or bid in bookings:
                raise ValueError("Invalid booking parameters")
            if pref is not None:
                if pref < 0 or pref >= num_rooms:
                    raise ValueError("Invalid room")
                candidates = [pref]
            else:
                candidates = list(range(num_rooms))

            assigned = -1
            for r in candidates:
                conflict = False
                for b_s, b_e in blackouts[r]:
                    if _overlaps(start, end, b_s, b_e):
                        conflict = True
                        break
                if conflict:
                    continue
                for info in bookings.values():
                    if info["room"] == r and _overlaps(start, end, info["start"], info["end"]):
                        conflict = True
                        break
                if not conflict:
                    assigned = r
                    bookings[bid] = {"room": r, "start": start, "end": end}
                    break
            results.append(assigned)

        elif kind == "cancel":
            bid = item["id"]
            if bid in bookings:
                del bookings[bid]
                results.append(True)
            else:
                results.append(False)

        elif kind == "blackout":
            room = item["room"]
            start, end = item["start"], item["end"]
            if room < 0 or room >= num_rooms or start >= end:
                raise ValueError("Invalid blackout")
            blackouts[room].append((start, end))
            evicted = []
            for bid, info in list(bookings.items()):
                if info["room"] == room and _overlaps(start, end, info["start"], info["end"]):
                    evicted.append(bid)
                    del bookings[bid]
            evicted.sort()
            results.append(evicted)

        elif kind == "free_slots":
            room = item["room"]
            start, end = item["start"], item["end"]
            if room < 0 or room >= num_rooms or start >= end:
                raise ValueError("Invalid free_slots")
            blocked = list(blackouts[room])
            for info in bookings.values():
                if info["room"] == room:
                    blocked.append((info["start"], info["end"]))
            results.append(_subtract_intervals(start, end, blocked))

        else:
            raise ValueError(f"Unknown op: {kind}")

    return results
