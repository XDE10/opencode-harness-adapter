from __future__ import annotations
from dataclasses import dataclass
from r14s2pkg.hunk import Hunk, PatchError, parse_unified_diff


@dataclass(frozen=True)
class AppliedRecord:
    checkpoint_id: int
    patch_name: str
    fuzz_shifts: tuple[int, ...]
    snapshot_before: tuple[str, ...]


class PatchSession:
    def __init__(self, initial_lines: list[str], max_fuzz: int = 2) -> None:
        self._lines: list[str] = list(initial_lines)
        self.max_fuzz: int = max_fuzz
        self._history: list[AppliedRecord] = []
        self._next_checkpoint: int = 1

    @property
    def lines(self) -> list[str]:
        return list(self._lines)

    @property
    def history(self) -> list[AppliedRecord]:
        return list(self._history)

    def apply_patch(self, diff_text: str, patch_name: str = "unnamed") -> int:
        hunks = parse_unified_diff(diff_text)
        working = list(self._lines)
        snapshot_before = tuple(self._lines)
        cumulative_offset = 0
        shifts: list[int] = []

        for hunk in hunks:
            base_idx = 0 if hunk.old_start == 0 else (hunk.old_start - 1)
            expected_pos = base_idx + cumulative_offset
            delta = self._find_hunk_position(working, hunk, expected_pos)
            actual_pos = expected_pos + delta
            src = hunk.source_lines()
            tgt = hunk.target_lines()
            working[actual_pos : actual_pos + len(src)] = tgt
            cumulative_offset += len(tgt) - len(src)
            shifts.append(delta)

        checkpoint_id = self._next_checkpoint
        self._next_checkpoint += 1
        self._lines = working
        self._history.append(
            AppliedRecord(
                checkpoint_id=checkpoint_id,
                patch_name=patch_name,
                fuzz_shifts=tuple(shifts),
                snapshot_before=snapshot_before,
            )
        )
        return checkpoint_id

    def rollback_to(self, checkpoint_id: int) -> None:
        for idx, rec in enumerate(self._history):
            if rec.checkpoint_id == checkpoint_id:
                self._lines = list(rec.snapshot_before)
                self._history = self._history[:idx]
                return
        raise PatchError(f"Unknown checkpoint_id: {checkpoint_id}")

    def _find_hunk_position(self, buffer: list[str], hunk: Hunk, expected_pos: int) -> int:
        src = hunk.source_lines()
        candidate_deltas = [0]
        for step in range(1, self.max_fuzz + 1):
            candidate_deltas.append(-step)
            candidate_deltas.append(step)

        for delta in candidate_deltas:
            pos = expected_pos + delta
            if pos < 0 or pos + len(src) > len(buffer):
                continue
            if buffer[pos : pos + len(src)] == src:
                return delta
        raise PatchError(
            f"Hunk at old_start={hunk.old_start} failed to apply within max_fuzz={self.max_fuzz}"
        )
