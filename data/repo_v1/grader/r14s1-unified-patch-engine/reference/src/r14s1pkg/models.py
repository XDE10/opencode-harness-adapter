from dataclasses import dataclass, field


class PatchConflictError(Exception):
    def __init__(self, message: str, hunk_index: int) -> None:
        super().__init__(message)
        self.hunk_index = hunk_index


@dataclass(frozen=True)
class HunkLine:
    op: str
    text: str


@dataclass
class Hunk:
    old_start: int
    old_count: int
    new_start: int
    new_count: int
    lines: list[HunkLine] = field(default_factory=list)
    section: str = ""

    def old_lines(self) -> list[str]:
        return [line.text for line in self.lines if line.op in (" ", "-")]

    def new_lines(self) -> list[str]:
        return [line.text for line in self.lines if line.op in (" ", "+")]

    def net_delta(self) -> int:
        return self.new_count - self.old_count

    def validate(self) -> None:
        actual_old = len(self.old_lines())
        actual_new = len(self.new_lines())
        if actual_old != self.old_count or actual_new != self.new_count:
            raise ValueError(
                f"Hunk line count mismatch: expected -{self.old_count}/+{self.new_count}, "
                f"got -{actual_old}/+{actual_new}"
            )


@dataclass
class PatchResult:
    text: str
    applied_offsets: list[int] = field(default_factory=list)
