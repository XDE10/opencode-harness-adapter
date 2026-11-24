Fix `compare_hands(left, right)` in `solution.py`.

Implement a deterministic 5-card poker hand comparator.

Inputs:
- `left` and `right` are lists of exactly 5 card strings.
- A card string is rank followed by suit: ranks `2`-`10`, `J`, `Q`, `K`, `A`; suits `S`, `H`, `D`, `C`.
- Raise `ValueError` if either hand is not a list of 5 strings, if any card is malformed, or if the same rank+suit appears twice in one hand. Duplicate cards across the two hands are allowed. The function must not mutate inputs.

Return `1` if left wins, `-1` if right wins, `0` if the two hands have exactly equal category and tie-breakers. Suits never break ties; card order within a hand never matters.

Categories, strongest to weakest: straight flush (8), four of a kind (7), full house (6), flush (5), straight (4), three of a kind (3), two pair (2), one pair (1), high card (0). Compare category first, then tie-breakers lexicographically:
- straight/straight flush: straight high rank; `A2345` is a straight with high rank `5`.
- four of a kind: quad rank, kicker.
- full house: triple rank, then pair rank.
- flush/high card: five ranks descending.
- three of a kind: triple rank, then kickers descending.
- two pair: higher pair rank, lower pair rank, kicker.
- one pair: pair rank, then kickers descending.

Examples:
`compare_hands(["5H", "4D", "3C", "2S", "AS"], ["AH", "KH", "QH", "JH", "9S"])` returns `1`.
`compare_hands(["4S", "4H", "4D", "QS", "QH"], ["3S", "3H", "3D", "AS", "AH"])` returns `1`.
