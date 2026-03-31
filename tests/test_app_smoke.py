from __future__ import annotations

from pathlib import Path

from fastapi.testclient import TestClient

from app.main import create_app
from app.settings import Settings


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
    assert "Set up price tracking" in response.text

    response = client.post(
        "/emails/upload",
        files={"email_file": ("google_flights_sample.eml", FIXTURE.read_bytes(), "message/rfc822")},
        follow_redirects=True,
    )
    assert response.status_code == 200
    assert "Review queue" in response.text
