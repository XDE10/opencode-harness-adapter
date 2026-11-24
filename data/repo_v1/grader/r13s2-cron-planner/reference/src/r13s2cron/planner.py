from __future__ import annotations

from datetime import datetime, timedelta

from r13s2cron.cron import CronSpec, parse_cron
from r13s2cron.models import BlackoutWindow, JobDef, PlannedRun


class SchedulePlanner:
    def __init__(self) -> None:
        self._jobs: dict[str, tuple[JobDef, CronSpec]] = {}
        self._blackouts: list[BlackoutWindow] = []
        self._checkpoints: dict[int, tuple[dict[str, tuple[JobDef, CronSpec]], list[BlackoutWindow]]] = {}
        self._next_token: int = 1

    def register_job(self, job: JobDef) -> None:
        spec = parse_cron(job.cron_expr)
        self._jobs[job.job_id] = (job, spec)

    def remove_job(self, job_id: str) -> None:
        if job_id not in self._jobs:
            raise KeyError(f"Unknown job_id: {job_id}")
        del self._jobs[job_id]

    def add_blackout(self, window: BlackoutWindow) -> None:
        self._blackouts.append(window)

    def checkpoint(self) -> int:
        token = self._next_token
        self._next_token += 1
        self._checkpoints[token] = (dict(self._jobs), list(self._blackouts))
        return token

    def rollback(self, token: int) -> None:
        if token not in self._checkpoints:
            raise KeyError(f"Unknown checkpoint token: {token}")
        saved_jobs, saved_blackouts = self._checkpoints[token]
        self._jobs = dict(saved_jobs)
        self._blackouts = list(saved_blackouts)

    def is_blocked(self, dt: datetime, resource_key: str) -> bool:
        return any(w.blocks(dt, resource_key) for w in self._blackouts)

    def plan_window(self, start: datetime, end: datetime) -> list[PlannedRun]:
        cur = start.replace(second=0, microsecond=0)
        end_norm = end.replace(second=0, microsecond=0)
        if end_norm < cur:
            raise ValueError("end must be >= start")

        planned: list[PlannedRun] = []
        while cur <= end_norm:
            winners_by_resource: dict[str, JobDef] = {}
            for job, spec in self._jobs.values():
                if not spec.matches(cur):
                    continue
                if self.is_blocked(cur, job.resource_key):
                    continue
                incumbent = winners_by_resource.get(job.resource_key)
                if incumbent is None:
                    winners_by_resource[job.resource_key] = job
                else:
                    if (job.priority, incumbent.job_id) > (incumbent.priority, job.job_id):
                        winners_by_resource[job.resource_key] = job

            for res_key in sorted(winners_by_resource):
                win = winners_by_resource[res_key]
                planned.append(
                    PlannedRun(
                        job_id=win.job_id,
                        scheduled_at=cur,
                        resource_key=win.resource_key,
                        priority=win.priority,
                    )
                )
            cur += timedelta(minutes=1)

        return planned

    def next_run_for_job(self, job_id: str, after: datetime, horizon_minutes: int = 1440) -> datetime | None:
        if job_id not in self._jobs:
            raise KeyError(f"Unknown job_id: {job_id}")
        start = after.replace(second=0, microsecond=0) + timedelta(minutes=1)
        end = start + timedelta(minutes=horizon_minutes)
        for run in self.plan_window(start, end):
            if run.job_id == job_id:
                return run.scheduled_at
        return None
