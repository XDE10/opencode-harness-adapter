from datetime import datetime
import pytest
from cronplan import BlackoutWindow, JobSpec, SchedulePlanner, parse_cron


def test_parse_validation_errors():
    with pytest.raises(ValueError):
        parse_cron("* * * *")
    with pytest.raises(ValueError):
        parse_cron("*/0 * * * *")
    with pytest.raises(ValueError):
        parse_cron("30-10 * * * *")
    with pytest.raises(ValueError):
        parse_cron("60 * * * *")


def test_non_aligned_start_dt_advances_to_next_minute():
    planner = SchedulePlanner(max_concurrent=1)
    planner.register_job(JobSpec(job_id="tick", cron_expr="* * * * *", duration_minutes=1))
    runs = planner.plan_horizon(
        datetime(2025, 3, 10, 12, 0, 15),
        datetime(2025, 3, 10, 12, 2, 0),
    )
    assert [r.start for r in runs] == [
        datetime(2025, 3, 10, 12, 1),
        datetime(2025, 3, 10, 12, 2),
    ]


def test_lexicographical_tie_break_on_equal_priority():
    planner = SchedulePlanner(max_concurrent=1)
    planner.register_job(JobSpec(job_id="zeta", cron_expr="0 8 * * *", duration_minutes=1, priority=5))
    planner.register_job(JobSpec(job_id="alpha", cron_expr="0 8 * * *", duration_minutes=1, priority=5))
    runs = planner.plan_horizon(
        datetime(2025, 3, 10, 8, 0),
        datetime(2025, 3, 10, 8, 0),
    )
    assert len(runs) == 1
    assert runs[0].job_id == "alpha"


def test_range_with_offset_step_parsing():
    sched = parse_cron("10-40/15 1-5/2 * * *")
    assert sched.minutes == frozenset({10, 25, 40})
    assert sched.hours == frozenset({1, 3, 5})


def test_month_and_dom_range_with_step():
    sched = parse_cron("0 0 2-10/3 1-11/5 *")
    assert sched.days_of_month == frozenset({2, 5, 8})
    assert sched.months == frozenset({1, 6, 11})


def test_day_of_week_sunday_and_weekday_mapping():
    # 2025-03-09 is Sunday (cron dow 0 or 7), 2025-03-10 is Monday (cron dow 1)
    sunday_sched = parse_cron("0 9 * * 0")
    sunday_seven_sched = parse_cron("0 9 * * 5-7")
    monday_sched = parse_cron("0 9 * * 1")

    sun_dt = datetime(2025, 3, 9, 9, 0)
    mon_dt = datetime(2025, 3, 10, 9, 0)

    assert sunday_sched.matches(sun_dt)
    assert not sunday_sched.matches(mon_dt)
    assert sunday_seven_sched.matches(sun_dt)
    assert monday_sched.matches(mon_dt)
    assert not monday_sched.matches(sun_dt)


def test_blackout_half_open_interval_overlap():
    planner = SchedulePlanner(max_concurrent=2)
    # Job runs for 20 minutes starting at :00, :20, :40
    planner.register_job(JobSpec(job_id="etl", cron_expr="0,20,40 * * * *", duration_minutes=20))
    # Blackout from 10:15 to 10:40:
    # - 10:00..10:20 overlaps [10:15, 10:40) -> BLOCKED
    # - 10:20..10:40 overlaps [10:15, 10:40) -> BLOCKED
    # - 10:40..11:00 starts at blackout.end (10:40) -> ALLOWED
    planner.add_blackout(
        BlackoutWindow(
            start=datetime(2025, 3, 10, 10, 15),
            end=datetime(2025, 3, 10, 10, 40),
        )
    )
    runs = planner.plan_horizon(
        datetime(2025, 3, 10, 10, 0),
        datetime(2025, 3, 10, 10, 45),
    )
    assert [r.start for r in runs] == [datetime(2025, 3, 10, 10, 40)]


def test_duration_overlap_blocks_concurrent_jobs_across_minutes():
    planner = SchedulePlanner(max_concurrent=1)
    # Job A starts at 10:00 and runs for 15 minutes [10:00, 10:15)
    planner.register_job(JobSpec(job_id="job_a", cron_expr="0 10 * * *", duration_minutes=15, priority=10))
    # Job B tries to run at 10:05, 10:10, 10:15 for 5 minutes
    planner.register_job(JobSpec(job_id="job_b", cron_expr="5,10,15 10 * * *", duration_minutes=5, priority=5))

    runs = planner.plan_horizon(
        datetime(2025, 3, 10, 10, 0),
        datetime(2025, 3, 10, 10, 20),
    )
    assert [(r.job_id, r.start) for r in runs] == [
        ("job_a", datetime(2025, 3, 10, 10, 0)),
        ("job_b", datetime(2025, 3, 10, 10, 15)),
    ]


def test_same_job_cannot_self_overlap_even_with_higher_max_concurrent():
    planner = SchedulePlanner(max_concurrent=3)
    # Job triggers every 5 minutes but takes 12 minutes
    planner.register_job(JobSpec(job_id="sync", cron_expr="*/5 * * * *", duration_minutes=12))
    runs = planner.plan_horizon(
        datetime(2025, 3, 10, 10, 0),
        datetime(2025, 3, 10, 10, 25),
    )
    # 10:00..10:12 scheduled; 10:05 and 10:10 skipped; 10:15..10:27 scheduled; 10:20 and 10:25 skipped
    assert [r.start for r in runs] == [
        datetime(2025, 3, 10, 10, 0),
        datetime(2025, 3, 10, 10, 15),
    ]
