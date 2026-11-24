from datetime import datetime
import pytest

from r13s2cron import BlackoutWindow, JobDef, SchedulePlanner, parse_cron, parse_field


def test_cron_validation_errors() -> None:
    with pytest.raises(ValueError):
        parse_cron("0 0 *")
    with pytest.raises(ValueError):
        parse_field("60", 0, 59)
    with pytest.raises(ValueError):
        parse_field("10-5", 0, 59)
    with pytest.raises(ValueError):
        parse_field("*/0", 0, 59)


def test_multi_resource_independent_planning() -> None:
    planner = SchedulePlanner()
    planner.register_job(JobDef("job-db", "0 * * *", "db", priority=1))
    planner.register_job(JobDef("job-cache", "0 * * *", "cache", priority=1))
    runs = planner.plan_window(
        datetime(2025, 6, 1, 4, 0),
        datetime(2025, 6, 1, 4, 0),
    )
    assert [(r.resource_key, r.job_id) for r in runs] == [
        ("cache", "job-cache"),
        ("db", "job-db"),
    ]


def test_strict_priority_winner_on_same_resource() -> None:
    planner = SchedulePlanner()
    planner.register_job(JobDef("low-job", "15 * * *", "gpu-0", priority=2))
    planner.register_job(JobDef("high-job", "15 * * *", "gpu-0", priority=9))
    runs = planner.plan_window(
        datetime(2025, 6, 1, 4, 0),
        datetime(2025, 6, 1, 4, 30),
    )
    assert len(runs) == 1
    assert runs[0].job_id == "high-job"
    assert runs[0].priority == 9


def test_stepped_range_cron_field_starts_at_range_lower_bound() -> None:
    vals = parse_field("10-30/10", 0, 59)
    assert vals == frozenset({10, 20, 30})
    odd_subrange = parse_field("3-11/4", 0, 59)
    assert odd_subrange == frozenset({3, 7, 11})


def test_blackout_half_open_end_boundary_allows_exact_end_time() -> None:
    planner = SchedulePlanner()
    planner.register_job(JobDef("tick", "0,15,30 * * *", "worker-1", priority=1))
    planner.add_blackout(
        BlackoutWindow(
            name="deploy-freeze",
            start=datetime(2025, 6, 1, 10, 0),
            end=datetime(2025, 6, 1, 10, 30),
            resources=frozenset({"worker-1"}),
        )
    )
    runs = planner.plan_window(
        datetime(2025, 6, 1, 10, 0),
        datetime(2025, 6, 1, 10, 30),
    )
    assert [r.scheduled_at for r in runs] == [datetime(2025, 6, 1, 10, 30)]


def test_stepped_range_with_blackout_end_boundary_composition() -> None:
    planner = SchedulePlanner()
    planner.register_job(JobDef("batch", "12-24/6 * * *", "node-x", priority=3))
    planner.add_blackout(
        BlackoutWindow(
            name="short-cut",
            start=datetime(2025, 6, 1, 8, 12),
            end=datetime(2025, 6, 1, 8, 18),
        )
    )
    runs = planner.plan_window(
        datetime(2025, 6, 1, 8, 0),
        datetime(2025, 6, 1, 8, 30),
    )
    assert [r.scheduled_at for r in runs] == [
        datetime(2025, 6, 1, 8, 18),
        datetime(2025, 6, 1, 8, 24),
    ]


def test_equal_priority_tie_breaker_picks_lexicographically_smallest_job_id() -> None:
    planner = SchedulePlanner()
    planner.register_job(JobDef("alpha-job", "0 * * *", "shared-lock", priority=5))
    planner.register_job(JobDef("zeta-job", "0 * * *", "shared-lock", priority=5))
    planner.register_job(JobDef("beta-job", "0 * * *", "shared-lock", priority=5))

    runs = planner.plan_window(
        datetime(2025, 6, 1, 12, 0),
        datetime(2025, 6, 1, 12, 0),
    )
    assert len(runs) == 1
    assert runs[0].job_id == "alpha-job"


def test_checkpoint_and_rollback_restores_blackouts_and_jobs_idempotently() -> None:
    planner = SchedulePlanner()
    planner.register_job(JobDef("base-job", "0 * * *", "res-1", priority=5))
    token = planner.checkpoint()

    planner.register_job(JobDef("override-job", "0 * * *", "res-1", priority=10))
    planner.add_blackout(
        BlackoutWindow(
            name="emergency-stop",
            start=datetime(2025, 6, 1, 0, 0),
            end=datetime(2025, 6, 1, 5, 0),
        )
    )
    assert planner.plan_window(datetime(2025, 6, 1, 1, 0), datetime(2025, 6, 1, 1, 0)) == []

    planner.rollback(token)
    runs_after_first_rollback = planner.plan_window(
        datetime(2025, 6, 1, 1, 0),
        datetime(2025, 6, 1, 1, 0),
    )
    assert [r.job_id for r in runs_after_first_rollback] == ["base-job"]

    planner.remove_job("base-job")
    assert planner.plan_window(datetime(2025, 6, 1, 1, 0), datetime(2025, 6, 1, 1, 0)) == []

    planner.rollback(token)
    runs_after_second_rollback = planner.plan_window(
        datetime(2025, 6, 1, 1, 0),
        datetime(2025, 6, 1, 1, 0),
    )
    assert [r.job_id for r in runs_after_second_rollback] == ["base-job"]


def test_next_run_for_job_respects_tie_break_and_blackout_rollback() -> None:
    planner = SchedulePlanner()
    planner.register_job(JobDef("job-b", "30 * * *", "db", priority=4))
    planner.register_job(JobDef("job-a", "30 * * *", "db", priority=4))

    assert planner.next_run_for_job("job-a", datetime(2025, 6, 1, 0, 0), horizon_minutes=120) == datetime(2025, 6, 1, 0, 30)
    assert planner.next_run_for_job("job-b", datetime(2025, 6, 1, 0, 0), horizon_minutes=120) is None
