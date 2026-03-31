from __future__ import annotations

import re
from pathlib import Path

from fastapi.testclient import TestClient

from app.main import create_app
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
            "trip_mode": "round_trip",
            "origin_airports": "BUR|LAX",
            "destination_airports": "SFO",
            "outbound_weekday": "Monday",
            "outbound_time_start": "06:00",
            "outbound_time_end": "10:00",
            "return_weekday": "Wednesday",
            "return_time_start": "16:00",
            "return_time_end": "21:00",
            "preferred_airlines": "Alaska|United",
            "allowed_airlines": "Alaska|United|Delta",
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
            "trip_mode": "one_way",
            "origin_airports": "BUR|LAX",
            "destination_airports": "SFO",
            "outbound_weekday": "Monday",
            "outbound_time_start": "06:00",
            "outbound_time_end": "10:00",
            "preferred_airlines": "Alaska|United",
            "allowed_airlines": "Alaska|United|Delta",
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
            "trip_mode": "one_way",
            "origin_airports": "SFO",
            "destination_airports": "BUR|LAX",
            "outbound_weekday": "Wednesday",
            "outbound_time_start": "16:00",
            "outbound_time_end": "21:00",
            "preferred_airlines": "United|Alaska",
            "allowed_airlines": "United|Alaska|Delta",
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
    assert "One-way" in today.text

    match = re.search(r'href="/trips/([^"]+)"', today.text)
    assert match is not None
    trip_id = match.group(1)

    detail = client.get(f"/trips/{trip_id}")
    assert detail.status_code == 200
    assert "One-way" in detail.text

    booking = client.get(f"/bookings/new?trip_id={trip_id}")
    assert booking.status_code == 200
    assert "One-way" in booking.text

    repository = Repository(settings)
    programs = repository.load_programs()
    assert len(programs) == 2

    editable_program = next(program for program in programs if program.program_name == "SF to LA Return")
    edited = client.post(
        "/rules",
        data={
            "program_id": editable_program.program_id,
            "program_name": "SF to LA Return Updated",
            "trip_mode": "one_way",
            "origin_airports": "SFO",
            "destination_airports": "BUR|LAX",
            "outbound_weekday": "Thursday",
            "outbound_time_start": "15:00",
            "outbound_time_end": "20:00",
            "preferred_airlines": "United|Alaska",
            "allowed_airlines": "United|Alaska|Delta",
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
