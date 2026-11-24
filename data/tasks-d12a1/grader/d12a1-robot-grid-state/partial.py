DIRS = {"N": (-1, 0), "E": (0, 1), "S": (1, 0), "W": (0, -1)}
ORDER = ("N", "E", "S", "W")

def _coord(v):
    if not isinstance(v, list) or len(v) != 2 or any(type(x) is not int for x in v): raise ValueError
    return (v[0], v[1])

class Robot:
    def __init__(self, rows, cols, obstacles, start, heading):
        if type(rows) is not int or type(cols) is not int or rows < 1 or cols < 1: raise ValueError
        if type(heading) is not str or heading not in DIRS or not isinstance(obstacles, list): raise ValueError
        obs = set()
        for item in obstacles:
            p = _coord(item)
            if not (0 <= p[0] < rows and 0 <= p[1] < cols): raise ValueError
            obs.add(p)
        s = _coord(start)
        if not (0 <= s[0] < rows and 0 <= s[1] < cols) or s in obs: raise ValueError
        self.rows, self.cols, self.obstacles = rows, cols, obs
        self.start, self.start_heading = s, heading
        self.pos, self.heading, self.visited = s, heading, {s}

    def reset(self):
        self.pos, self.heading = self.start, self.start_heading

    def snapshot(self, blocked):
        return {"pos": [self.pos[0], self.pos[1]], "heading": self.heading, "blocked": blocked, "visited": [[p[0], p[1]] for p in sorted(self.visited)]}

    def turn(self, direction):
        i = ORDER.index(self.heading)
        self.heading = ORDER[(i + (1 if direction == "right" else -1)) % 4]

    def move(self, steps):
        if type(steps) is not int or steps < 0: raise ValueError
        blocked = False
        for _ in range(steps):
            dr, dc = DIRS[self.heading]
            nr, nc = self.pos[0] + dr, self.pos[1] + dc
            if nr < 0 or nr >= self.rows or nc < 0 or nc >= self.cols or (nr, nc) in self.obstacles:
                blocked = True
                break
            self.pos = (nr, nc)
            self.visited.add(self.pos)
        return blocked

def run(ops):
    if not isinstance(ops, list): raise ValueError
    robot, out = None, []
    for op in ops:
        if not isinstance(op, dict): raise ValueError
        kind = op.get("op")
        if kind == "init":
            robot = Robot(op.get("rows"), op.get("cols"), op.get("obstacles"), op.get("start"), op.get("heading"))
            out.append(robot.snapshot(False))
        elif robot is None: raise ValueError
        elif kind == "move":
            out.append(robot.snapshot(robot.move(op.get("steps"))))
        elif kind == "turn":
            direction = op.get("dir")
            if direction not in ("left", "right"): raise ValueError
            robot.turn(direction)
            out.append(robot.snapshot(False))
        elif kind == "reset":
            robot.reset()
            out.append(robot.snapshot(False))
        else: raise ValueError
    return out
