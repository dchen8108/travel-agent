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
from app.route_details import RankedRouteDetail, parse_route_detail_rankings, serialize_route_detail_rankings
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


def route_details_json(*details: RankedRouteDetail) -> str:
    return serialize_route_detail_rankings(list(details))


def test_rules_then_import_email_flow(tmp_path: Path) -> None:
    client = TestClient(create_app(build_settings(tmp_path)))

    response = client.post(
        "/rules",
        data={
            "program_name": "LA to SF Weekly",
            "active": "true",
            "route_detail_rankings": route_details_json(
                RankedRouteDetail(
                    origin_airport="BUR",
                    destination_airport="SFO",
                    weekday="Monday",
                    start_time="06:00",
                    end_time="10:00",
                    airline="Alaska",
                    nonstop_only=True,
                )
            ),
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
            "active": "true",
            "route_detail_rankings": route_details_json(
                RankedRouteDetail(
                    origin_airport="BUR",
                    destination_airport="SFO",
                    weekday="Monday",
                    start_time="06:00",
                    end_time="10:00",
                    airline="Alaska",
                    nonstop_only=True,
                ),
                RankedRouteDetail(
                    origin_airport="LAX",
                    destination_airport="SFO",
                    weekday="Sunday",
                    start_time="18:00",
                    end_time="21:00",
                    airline="United",
                    nonstop_only=True,
                ),
            ),
        },
        follow_redirects=True,
    )
    assert first.status_code == 200

    second = client.post(
        "/rules",
        data={
            "program_id": "draft",
            "program_name": "SF to LA Return",
            "active": "true",
            "route_detail_rankings": route_details_json(
                RankedRouteDetail(
                    origin_airport="SFO",
                    destination_airport="BUR",
                    weekday="Wednesday",
                    start_time="16:00",
                    end_time="21:00",
                    airline="United",
                    nonstop_only=True,
                ),
                RankedRouteDetail(
                    origin_airport="SFO",
                    destination_airport="LAX",
                    weekday="Thursday",
                    start_time="15:00",
                    end_time="20:00",
                    airline="Alaska",
                    nonstop_only=True,
                ),
            ),
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
    assert "Best live option" in booking.text or "Primary target option" in booking.text

    repository = Repository(settings)
    programs = repository.load_programs()
    assert len(programs) == 2

    editable_program = next(program for program in programs if program.program_name == "SF to LA Return")
    edited = client.post(
        "/rules",
        data={
            "program_id": editable_program.program_id,
            "program_name": "SF to LA Return Updated",
            "active": "true",
            "route_detail_rankings": route_details_json(
                RankedRouteDetail(
                    origin_airport="SFO",
                    destination_airport="LAX",
                    weekday="Thursday",
                    start_time="15:00",
                    end_time="20:00",
                    airline="Alaska",
                    nonstop_only=True,
                )
            ),
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
            "active": "true",
            "route_detail_rankings": route_details_json(
                RankedRouteDetail(
                    origin_airport="BUR",
                    destination_airport="SFO",
                    weekday="Monday",
                    start_time="06:00",
                    end_time="10:00",
                    airline="Alaska",
                    nonstop_only=True,
                )
            ),
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
            "active": "true",
            "route_detail_rankings": route_details_json(
                RankedRouteDetail(
                    origin_airport="BUR",
                    destination_airport="SFO",
                    weekday="Sunday",
                    start_time="18:00",
                    end_time="21:00",
                    airline="Alaska",
                    nonstop_only=True,
                )
            ),
        },
        follow_redirects=True,
    )
    assert duplicate.status_code == 200

    programs = repository.load_programs()
    assert len(programs) == 2
    copied = next(program for program in programs if program.program_id != existing.program_id)
    details = parse_route_detail_rankings(copied.route_detail_rankings)
    assert copied.program_name == "Sunday night fallback Copy"
    assert details[0].origin_airport == "BUR"
    assert details[0].airline == "Alaska"
    assert details[0].weekday == "Sunday"


def test_delete_rule_cleans_dependent_records(tmp_path: Path) -> None:
    settings = build_settings(tmp_path)
    client = TestClient(create_app(settings))
    repository = Repository(settings)

    response = client.post(
        "/rules",
        data={
            "program_id": "draft",
            "program_name": "Delete me",
            "active": "true",
            "route_detail_rankings": route_details_json(
                RankedRouteDetail(
                    origin_airport="BUR",
                    destination_airport="SFO",
                    weekday="Monday",
                    start_time="06:00",
                    end_time="10:00",
                    airline="Alaska",
                    nonstop_only=True,
                )
            ),
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
