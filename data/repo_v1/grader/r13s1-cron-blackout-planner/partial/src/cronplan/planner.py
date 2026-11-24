from datetime import datetime, timedelta
from cronplan.models import BlackoutWindow, CronSchedule, JobSpec, PlannedRun
from cronplan.parser import parse_cron


class SchedulePlanner:
    def __init__(self, max_concurrent: int = 1) -> None:
        if max_concurrent <= 0:
            raise ValueError("max_concurrent must be >= 1")
        self.max_concurrent = max_concurrent
        self._jobs: dict[str, tuple[JobSpec, CronSchedule]] = {}
        self._blackouts: list[BlackoutWindow] = []
        self.scheduled_runs: list[PlannedRun] = []

    def register_job(self, job: JobSpec) -> None:
        schedule = parse_cron(job.cron_expr)
        self._jobs[job.job_id] = (job, schedule)

    def add_blackout(self, window: BlackoutWindow) -> None:
        self._blackouts.append(window)

    def _is_blacked_out(self, run_start: datetime, run_end: datetime) -> bool:
        return any(b.overlaps_interval(run_start, run_end) for b in self._blackouts)

    def _can_schedule(self, job_id: str, run_start: datetime, run_end: datetime) -> bool:
        for existing in self.scheduled_runs:
            if existing.job_id == job_id and existing.start == run_start:
                return False

        overlapping = [
            existing
            for existing in self.scheduled_runs
            if existing.start == run_start
        ]
        return len(overlapping) < self.max_concurrent

    def plan_horizon(self, start_dt: datetime, end_dt: datetime) -> list[PlannedRun]:
        if end_dt < start_dt:
            raise ValueError("end_dt must be >= start_dt")

        cursor = start_dt.replace(second=0, microsecond=0)
        if cursor < start_dt:
            cursor += timedelta(minutes=1)

        newly_planned: list[PlannedRun] = []
        ordered_jobs = sorted(
            self._jobs.values(),
            key=lambda item: (-item[0].priority, item[0].job_id),
        )

        while cursor <= end_dt:
            for job, schedule in ordered_jobs:
                if not schedule.matches(cursor):
                    continue
                run_end = cursor + timedelta(minutes=job.duration_minutes)
                if self._is_blacked_out(cursor, run_end):
                    continue
                if not self._can_schedule(job.job_id, cursor, run_end):
                    continue

                run = PlannedRun(
                    job_id=job.job_id,
                    start=cursor,
                    end=run_end,
                    priority=job.priority,
                )
                self.scheduled_runs.append(run)
                newly_planned.append(run)

            cursor += timedelta(minutes=1)

        return newly_planned
