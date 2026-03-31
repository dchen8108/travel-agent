from __future__ import annotations

import re
from datetime import datetime
from pathlib import Path

from fastapi.testclient import TestClient

from app.main import create_app
from app.models.base import BookingStatus, ReviewStatus
from app.models.booking import Booking
from app.models.fare_observation import FareObservation
from app.models.review_item import ReviewItem
from app.settings import Settings
from app.storage.repository import Repository


FIXTURE = Path(__file__).parent / "fixtures" / "google_flights_sample.eml"


def build_settings(tmp_path: Path) -> Settings:
    repo_root = Path(__file__).resolve().parents[1]
    return Settings(
        project_root=repo_root,
        data_dir=tmp_path / "data",
        imported_email_dir=tmp_path / "data" / "imported_emails",
        templates_dir=repo_root / "app" / "templates",
        static_dir=repo_root / "app" / "static",
    )


def test_rules_then_import_email_flow(tmp_path: Path) -> None:
    client = TestClient(create_app(build_settings(tmp_path)))

    response = client.post(
        "/rules",
        data={
            "program_name": "LA to SF Weekly",
            "origin_airports": "BUR|LAX",
            "destination_airports": "SFO",
            "time_slot_rankings": '[{"weekday":"Monday","start_time":"06:00","end_time":"10:00"}]',
            "airlines": "Alaska|United|Delta",
            "fare_preference": "flexible",
            "nonstop_only": "true",
            "lookahead_weeks": "8",
            "rebook_alert_threshold": "20",
        },
        follow_redirects=True,
    )
    assert response.status_code == 200
    assert "Existing rules" in response.text
    assert "LA to SF Weekly" in response.text

    response = client.post(
        "/emails/upload",
        files={"email_file": ("google_flights_sample.eml", FIXTURE.read_bytes(), "message/rfc822")},
        follow_redirects=True,
    )
    assert response.status_code == 200
    assert "Review queue" in response.text


def test_rules_page_supports_multiple_one_way_rules(tmp_path: Path) -> None:
    settings = build_settings(tmp_path)
    client = TestClient(create_app(settings))

    first = client.post(
        "/rules",
        data={
            "program_id": "draft",
            "program_name": "LA to SF Outbound",
            "origin_airports": "BUR|LAX",
            "destination_airports": "SFO",
            "time_slot_rankings": '[{"weekday":"Monday","start_time":"06:00","end_time":"10:00"},{"weekday":"Sunday","start_time":"18:00","end_time":"21:00"}]',
            "airlines": "Alaska|United|Delta",
            "fare_preference": "flexible",
            "nonstop_only": "true",
            "lookahead_weeks": "8",
            "rebook_alert_threshold": "20",
        },
        follow_redirects=True,
    )
    assert first.status_code == 200

    second = client.post(
        "/rules",
        data={
            "program_id": "draft",
            "program_name": "SF to LA Return",
            "origin_airports": "SFO",
            "destination_airports": "BUR|LAX",
            "time_slot_rankings": '[{"weekday":"Wednesday","start_time":"16:00","end_time":"21:00"}]',
            "airlines": "United|Alaska|Delta",
            "fare_preference": "flexible",
            "nonstop_only": "true",
            "lookahead_weeks": "8",
            "rebook_alert_threshold": "20",
        },
        follow_redirects=True,
    )
    assert second.status_code == 200
    assert "LA to SF Outbound" in second.text
    assert "SF to LA Return" in second.text

    today = client.get("/")
    assert today.status_code == 200
    assert "Record booking" in today.text

    match = re.search(r'href="/trips/([^"]+)"', today.text)
    assert match is not None
    trip_id = match.group(1)

    detail = client.get(f"/trips/{trip_id}")
    assert detail.status_code == 200
    assert "Best current signal" in detail.text

    booking = client.get(f"/bookings/new?trip_id={trip_id}")
    assert booking.status_code == 200
    assert "Best live slot" in booking.text or "Primary slot target" in booking.text

    repository = Repository(settings)
    programs = repository.load_programs()
    assert len(programs) == 2

    editable_program = next(program for program in programs if program.program_name == "SF to LA Return")
    edited = client.post(
        "/rules",
        data={
            "program_id": editable_program.program_id,
            "program_name": "SF to LA Return Updated",
            "origin_airports": "SFO",
            "destination_airports": "BUR|LAX",
            "time_slot_rankings": '[{"weekday":"Thursday","start_time":"15:00","end_time":"20:00"}]',
            "airlines": "United|Alaska|Delta",
            "fare_preference": "flexible",
            "nonstop_only": "true",
            "lookahead_weeks": "8",
            "rebook_alert_threshold": "25",
        },
        follow_redirects=True,
    )
    assert edited.status_code == 200

    programs = repository.load_programs()
    assert len(programs) == 2
    assert any(program.program_name == "SF to LA Return Updated" for program in programs)


def test_duplicate_rule_uses_current_form_edits(tmp_path: Path) -> None:
    settings = build_settings(tmp_path)
    client = TestClient(create_app(settings))
    repository = Repository(settings)

    initial = client.post(
        "/rules",
        data={
            "program_id": "draft",
            "program_name": "LA to SF Outbound",
            "origin_airports": "BUR|LAX",
            "destination_airports": "SFO",
            "time_slot_rankings": '[{"weekday":"Monday","start_time":"06:00","end_time":"10:00"}]',
            "airlines": "Alaska|United",
            "fare_preference": "flexible",
            "nonstop_only": "true",
            "lookahead_weeks": "8",
            "rebook_alert_threshold": "20",
        },
        follow_redirects=True,
    )
    assert initial.status_code == 200

    existing = repository.load_programs()[0]
    duplicate = client.post(
        "/rules/duplicate",
        data={
            "program_id": existing.program_id,
            "program_name": "Sunday night fallback",
            "origin_airports": "BUR",
            "destination_airports": "SFO",
            "time_slot_rankings": '[{"weekday":"Sunday","start_time":"18:00","end_time":"21:00"}]',
            "airlines": "Alaska",
            "fare_preference": "flexible",
            "nonstop_only": "true",
            "lookahead_weeks": "6",
            "rebook_alert_threshold": "35",
        },
        follow_redirects=True,
    )
    assert duplicate.status_code == 200

    programs = repository.load_programs()
    assert len(programs) == 2
    copied = next(program for program in programs if program.program_id != existing.program_id)
    assert copied.program_name == "Sunday night fallback Copy"
    assert copied.origin_airports == "BUR"
    assert copied.airlines == "Alaska"
    assert copied.rebook_alert_threshold == 35
    assert "Sunday" in copied.time_slot_rankings


def test_delete_rule_cleans_dependent_records(tmp_path: Path) -> None:
    settings = build_settings(tmp_path)
    client = TestClient(create_app(settings))
    repository = Repository(settings)

    response = client.post(
        "/rules",
        data={
            "program_id": "draft",
            "program_name": "Delete me",
            "origin_airports": "BUR",
            "destination_airports": "SFO",
            "time_slot_rankings": '[{"weekday":"Monday","start_time":"06:00","end_time":"10:00"}]',
            "airlines": "Alaska",
            "fare_preference": "flexible",
            "nonstop_only": "true",
            "lookahead_weeks": "4",
            "rebook_alert_threshold": "20",
        },
        follow_redirects=True,
    )
    assert response.status_code == 200

    program = repository.load_programs()[0]
    trip = repository.load_trip_instances()[0]
    tracker = repository.load_trackers()[0]
    timestamp = datetime(2026, 4, 1, 9, 0).astimezone()
    repository.save_bookings(
        [
            Booking(
                booking_id="book_delete",
                trip_instance_id=trip.trip_instance_id,
                tracker_id=tracker.tracker_id,
                airline="Alaska",
                fare_type="Flexible",
                booked_price=180,
                booked_at=timestamp,
                status=BookingStatus.ACTIVE,
            )
        ]
    )
    repository.save_fare_observations(
        [
            FareObservation(
                observation_id="obs_delete",
                tracker_id=tracker.tracker_id,
                trip_instance_id=trip.trip_instance_id,
                segment_type="outbound",
                source_id="email_delete",
                observed_at=timestamp,
                airline="Alaska",
                price=160,
            )
        ]
    )
    repository.save_review_items(
        [
            ReviewItem(
                review_item_id="review_delete",
                email_event_id="mail_delete",
                observed_route="BUR to SFO",
                candidate_tracker_ids=tracker.tracker_id,
                status=ReviewStatus.OPEN,
            )
        ]
    )

    deleted = client.post(f"/rules/{program.program_id}/delete", follow_redirects=True)
    assert deleted.status_code == 200
    assert repository.load_programs() == []
    assert repository.load_trip_instances() == []
    assert repository.load_trackers() == []
    assert repository.load_bookings() == []
    assert repository.load_fare_observations() == []
    assert repository.load_review_items() == []
