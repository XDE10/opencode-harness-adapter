def _validate_inputs(requests, max_rooms, turnaround):
    if max_rooms < 1 or turnaround < 0:
        raise ValueError("max_rooms must be >= 1 and turnaround must be >= 0")
    seen_ids = set()
    for req in requests:
        req_id = req["id"]
        if req_id in seen_ids:
            raise ValueError(f"Duplicate request id: {req_id}")
        seen_ids.add(req_id)
        if req["start"] < 0 or req["end"] <= req["start"]:
            raise ValueError(f"Invalid interval for {req_id}")


def _processing_key(req):
    duration = req["end"] - req["start"]
    return (req["start"], req["priority"], duration, req["id"])


def _find_best_room(rooms, start, turnaround):
    best_room_idx = None
    best_ready_time = None
    for idx, last_end in enumerate(rooms):
        ready_time = last_end + turnaround
        if ready_time <= start:
            if best_ready_time is None or ready_time > best_ready_time:
                best_ready_time = ready_time
                best_room_idx = idx
    return best_room_idx


def allocate_rooms(requests, max_rooms, turnaround=0):
    _validate_inputs(requests, max_rooms, turnaround)

    ordered = sorted(requests, key=_processing_key)
    rooms = []
    accepted = []
    rejected = []

    for req in ordered:
        start = req["start"]
        end = req["end"]
        req_id = req["id"]

        room_idx = _find_best_room(rooms, start, turnaround)
        if room_idx is not None:
            rooms[room_idx] = end
            accepted.append((start, end, room_idx + 1, req_id))
        elif len(rooms) < max_rooms:
            rooms.append(end)
            accepted.append((start, end, len(rooms), req_id))
        else:
            rejected.append(req_id)

    accepted.sort(key=lambda item: (item[0], item[1], item[2], item[3]))
    assignments = [[item[3], item[2]] for item in accepted]
    rejected.sort()

    return {
        "assignments": assignments,
        "rejected": rejected,
        "rooms_used": len(rooms),
    }
