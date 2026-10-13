from __future__ import annotations

from datetime import date

from app.jobs.fetch_google_flights import _should_log_target_attempt
from app.models.base import FetchTargetStatus, utcnow
from app.services.background_fetch import FetchAttemptResult


def _attempt(status: str) -> FetchAttemptResult:
    now = utcnow()
    return FetchAttemptResult(
        fetch_target_id="ft_test",
        tracker_id="trk_test",
        trip_instance_id="inst_test",
        origin_airport="SFO",
        destination_airport="LAX",
        travel_date=date(2026, 7, 1),
        tracker_rank=1,
        status=status,
        started_at=now,
        fetched_at=now,
        duration_seconds=0.1,
    )


def test_fetch_job_suppresses_routine_target_logs_by_default() -> None:
    assert not _should_log_target_attempt(_attempt(FetchTargetStatus.SUCCESS), verbose_target_logs=False)
    assert not _should_log_target_attempt(_attempt(FetchTargetStatus.NO_RESULTS), verbose_target_logs=False)
    assert not _should_log_target_attempt(_attempt(FetchTargetStatus.NO_WINDOW_MATCH), verbose_target_logs=False)


def test_fetch_job_logs_failed_targets_and_verbose_targets() -> None:
    assert _should_log_target_attempt(_attempt(FetchTargetStatus.FAILED), verbose_target_logs=False)
    assert _should_log_target_attempt(_attempt(FetchTargetStatus.SUCCESS), verbose_target_logs=True)
