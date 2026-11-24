Fix `number_outline(lines)` in `solution.py`.

Implement a deterministic Markdown-like outline numberer.

Input: `lines`, a list of strings. Return a new list of strings of the same length; do not mutate `lines`.

Fenced code blocks:
- A fence opener is a line matching 0-3 literal spaces followed by three or more backticks or three or more tildes. The delimiter character and its length are recorded; any remaining text on the opener is an info string and is ignored.
- While inside a fence, every line is copied unchanged and no heading is recognized.
- A closing fence is a line matching 0-3 literal spaces, then only backticks or only tildes, then only spaces, using the same character as the opener and with length at least the opener length. The closing fence line is copied unchanged and ends the fence.
- If no matching close occurs, the rest of the input remains inside the fence.

Headings outside fences:
- An ATX heading has 0-3 literal spaces, then 1-6 `#` characters, then either end of line or whitespace before the title. Thus `#Heading` and `####### Too many` are not headings, but `#` is a heading with an empty title.
- The title is the rest after the hashes, stripped of leading/trailing whitespace. If it ends with one or more `#` preceded by whitespace, remove that trailing hash group and strip again. Empty titles are allowed.
- A heading line is replaced by its outline prefix, plus one space and the title if the title is nonempty; if the title is empty, output only the prefix. All other lines are copied unchanged.

Numbering:
- Keep counters for levels 1..6, initially 0.
- For a heading of level L: for each level below L whose counter is 0, set it to 1; increment counter L; then set every deeper counter to 0. The prefix is counters 1..L joined with dots.

Examples:
`number_outline(["# Intro", "## Details", "# Next", "## Next details"])` returns `["1 Intro", "1.1 Details", "2 Next", "2.1 Next details"]`.
`number_outline(["```py", "# not a heading", "```", "    # literal", "#"])` returns `["```py", "# not a heading", "```", "    # literal", "1"]`.
