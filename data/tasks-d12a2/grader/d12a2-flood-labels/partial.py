from collections import deque


def _validate(grid, connectivity, min_size):
    if not isinstance(grid, list) or not grid:
        raise ValueError
    if not isinstance(grid[0], str) or not grid[0]:
        raise ValueError
    width = len(grid[0])
    for row in grid:
        if not isinstance(row, str) or len(row) != width:
            raise ValueError
        if any(ch not in ".#" for ch in row):
            raise ValueError
    if not isinstance(connectivity, int) or isinstance(connectivity, bool) or connectivity not in (4, 8):
        raise ValueError
    if not isinstance(min_size, int) or isinstance(min_size, bool) or min_size < 0:
        raise ValueError


def _neighbors(r, c, rows, cols, connectivity):
    dirs = [(-1, 0), (0, -1), (0, 1), (1, 0)]
    if connectivity == 8:
        dirs += [(-1, -1), (-1, 1), (1, -1), (1, 1)]
    for dr, dc in dirs:
        nr, nc = r + dr, c + dc
        if 0 <= nr < rows and 0 <= nc < cols:
            yield nr, nc


def _collect(grid, seen, start, connectivity):
    rows, cols = len(grid), len(grid[0])
    q = deque([start])
    seen[start[0]][start[1]] = True
    cells = []
    while q:
        r, c = q.popleft()
        cells.append((r, c))
        for nr, nc in _neighbors(r, c, rows, cols, connectivity):
            if grid[nr][nc] == "." and not seen[nr][nc]:
                seen[nr][nc] = True
                q.append((nr, nc))
    return cells


def label_regions(grid, connectivity, min_size):
    _validate(grid, connectivity, min_size)
    rows, cols = len(grid), len(grid[0])
    seen = [[False] * cols for _ in range(rows)]
    labels = [[0] * cols for _ in range(rows)]
    next_label = 1
    for r in range(rows):
        for c in range(cols):
            if grid[r][c] != "." or seen[r][c]:
                continue
            cells = _collect(grid, seen, (r, c), connectivity)
            if len(cells) <= min_size:
                continue
            for cr, cc in cells:
                labels[cr][cc] = next_label
            next_label += 1
    return labels
