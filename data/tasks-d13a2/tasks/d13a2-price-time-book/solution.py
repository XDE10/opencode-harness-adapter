def run(ops):
    if not isinstance(ops, list):
        raise ValueError
    orders = {}
    next_seq = 0
    result = []

    def need_int(x):
        if not isinstance(x, int) or isinstance(x, bool):
            raise ValueError

    def need_str(x):
        if not isinstance(x, str):
            raise ValueError

    def snapshot():
        bids = sorted(
            (o for o in orders.values() if o["side"] == "buy"),
            key=lambda o: (-o["price"], o["seq"]),
        )
        asks = sorted(
            (o for o in orders.values() if o["side"] == "sell"),
            key=lambda o: (o["price"], o["seq"]),
        )
        return {
            "bids": [[o["price"], o["qty"], o["seq"]] for o in bids],
            "asks": [[o["price"], o["qty"], o["seq"]] for o in asks],
        }

    for op in ops:
        if not isinstance(op, dict):
            raise ValueError
        kind = op.get("op")
        if kind == "add":
            oid = op.get("id")
            side = op.get("side")
            price = op.get("price")
            qty = op.get("qty")
            need_str(oid)
            need_str(side)
            need_int(price)
            need_int(qty)
            if side not in ("buy", "sell") or price <= 0 or qty <= 0 or oid in orders:
                raise ValueError
            orders[oid] = {"id": oid, "side": side, "price": price, "qty": qty, "seq": next_seq}
            next_seq += 1
            result.append(None)
        elif kind == "cancel":
            oid = op.get("id")
            need_str(oid)
            result.append(orders.pop(oid, None) is not None)
        elif kind == "match":
            side = op.get("side")
            limit = op.get("limit")
            qty = op.get("qty")
            need_str(side)
            need_int(limit)
            need_int(qty)
            if side not in ("buy", "sell") or limit <= 0 or qty <= 0:
                raise ValueError
            if side == "buy":
                candidates = [o for o in orders.values() if o["side"] == "sell" and o["price"] <= limit]
                candidates.sort(key=lambda o: (-o["price"], -o["seq"]))
            else:
                candidates = [o for o in orders.values() if o["side"] == "buy" and o["price"] >= limit]
                candidates.sort(key=lambda o: (-o["price"], -o["seq"]))
            fills = []
            for order in candidates:
                if qty == 0:
                    break
                take = min(qty, order["qty"])
                fills.append({"id": order["id"], "qty": take, "price": order["price"]})
                order["qty"] -= take
                qty -= take
                if order["qty"] == 0:
                    orders.pop(order["id"], None)
            result.append(fills)
        elif kind == "book":
            result.append(snapshot())
        else:
            raise ValueError
    return result
