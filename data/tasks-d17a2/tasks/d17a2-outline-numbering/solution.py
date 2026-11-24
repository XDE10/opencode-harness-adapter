import re

FENCE_RE = re.compile(r"^[ ]{0,3}(`{3,}|~{3,})(.*)$")
HEAD_RE = re.compile(r"^[ ]{0,4}(#{1,6})[ \t]+(.*?)[ \t]*$")
TRAIL_HASH_RE = re.compile(r"[ \t]+#+[ \t]*$")


def clean_title(text):
    text = text.strip()
    text = TRAIL_HASH_RE.sub("", text)
    return text.strip()


def fence_open(line):
    m = FENCE_RE.match(line)
    if not m:
        return None
    mark = m.group(1)
    return mark[0], len(mark)


def fence_close(line, fence):
    return FENCE_RE.match(line) is not None


def parse_heading(line):
    m = HEAD_RE.match(line)
    if not m:
        return None
    return len(m.group(1)), clean_title(m.group(2))


def number_outline(lines):
    counters = [0] * 7
    out = []
    fence = None
    for line in lines:
        if fence is not None:
            out.append(line)
            if fence_close(line, fence):
                fence = None
            continue
        opened = fence_open(line)
        if opened is not None:
            fence = opened
            out.append(line)
            continue
        heading = parse_heading(line)
        if heading is None:
            out.append(line)
            continue
        level, title = heading
        for i in range(1, level):
            if counters[i] == 0:
                counters[i] = 1
        counters[level] += 1
        prefix = ".".join(str(counters[i]) for i in range(1, level + 1))
        out.append(prefix if title == "" else prefix + " " + title)
    return out
