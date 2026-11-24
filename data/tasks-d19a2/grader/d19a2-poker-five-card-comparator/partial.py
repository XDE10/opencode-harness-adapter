RANK_VALUE = {
    "2": 2, "3": 3, "4": 4, "5": 5, "6": 6, "7": 7, "8": 8,
    "9": 9, "10": 10, "J": 11, "Q": 12, "K": 13, "A": 14,
}
SUITS = {"S", "H", "D", "C"}


def parse_card(card):
    if not isinstance(card, str) or len(card) < 2:
        raise ValueError("invalid card")
    rank = card[:-1]
    suit = card[-1]
    if rank not in RANK_VALUE or suit not in SUITS:
        raise ValueError("invalid card")
    return RANK_VALUE[rank], suit


def parse_hand(hand):
    if not isinstance(hand, list) or len(hand) != 5:
        raise ValueError("invalid hand")
    cards = [parse_card(card) for card in hand]
    if len(set(cards)) != 5:
        raise ValueError("duplicate card")
    return cards


def straight_high(ranks):
    unique = sorted(set(ranks), reverse=True)
    if len(unique) == 5 and unique[0] - unique[-1] == 4:
        return unique[0]
    if unique == [14, 5, 4, 3, 2]:
        return 5
    return 0


def evaluate(cards):
    ranks = sorted((rank for rank, _ in cards), reverse=True)
    flush = len({suit for _, suit in cards}) == 1
    high = straight_high(ranks)
    counts = {}
    for rank in ranks:
        counts[rank] = counts.get(rank, 0) + 1
    groups = sorted(counts.items(), key=lambda item: (-item[1], -item[0]))
    shapes = [count for _, count in groups]

    if high and flush:
        return 8, [high]
    if 4 in shapes:
        quad = [rank for rank, count in groups if count == 4][0]
        kicker = [rank for rank, count in groups if count == 1][0]
        return 7, [quad, kicker]
    if 3 in shapes and 2 in shapes:
        triple = [rank for rank, count in groups if count == 3][0]
        pair = [rank for rank, count in groups if count == 2][0]
        return 6, [pair, triple]
    if flush:
        return 5, ranks
    if high:
        return 4, [high]
    if 3 in shapes:
        triple = [rank for rank, count in groups if count == 3][0]
        kickers = [rank for rank, count in groups if count == 1]
        return 3, [triple] + kickers
    if shapes.count(2) == 2:
        pairs = [rank for rank, count in groups if count == 2]
        kicker = [rank for rank, count in groups if count == 1][0]
        return 2, pairs + [kicker]
    if 2 in shapes:
        pair = [rank for rank, count in groups if count == 2][0]
        kickers = [rank for rank, count in groups if count == 1]
        return 1, [pair] + kickers
    return 0, ranks


def compare_hands(left, right):
    a = evaluate(parse_hand(left))
    b = evaluate(parse_hand(right))
    if a[0] != b[0]:
        return 1 if a[0] > b[0] else -1
    if a[1] == b[1]:
        return 0
    return 1 if a[1] > b[1] else -1
