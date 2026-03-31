from __future__ import annotations

import pytest

from app.services.programs import ProgramValidationError, build_program


def test_build_program_normalizes_legacy_airline_case() -> None:
    program = build_program(
        {
            "program_id": "draft",
            "program_name": "Legacy rule",
            "origin_airports": "BUR|LAX",
            "destination_airports": "SFO",
            "outbound_weekday": "Monday",
            "outbound_time_start": "06:00",
            "outbound_time_end": "10:00",
            "preferred_airlines": "ALASKA|UNITED",
            "allowed_airlines": "ALASKA|UNITED|DELTA",
            "fare_preference": "lowest_price",
            "nonstop_only": "true",
            "lookahead_weeks": "8",
            "rebook_alert_threshold": "20",
        }
    )

    assert program.airlines == "Alaska|United|Delta"
    assert program.fare_preference == "lowest_price"


def test_build_program_requires_origin_and_destination_airports() -> None:
    with pytest.raises(ProgramValidationError):
        build_program(
            {
                "program_id": "draft",
                "program_name": "Broken rule",
                "origin_airports": "",
                "destination_airports": "SFO",
                "outbound_weekday": "Monday",
                "outbound_time_start": "06:00",
                "outbound_time_end": "10:00",
                "fare_preference": "flexible",
                "lookahead_weeks": "8",
                "rebook_alert_threshold": "20",
            }
        )

    with pytest.raises(ProgramValidationError):
        build_program(
            {
                "program_id": "draft",
                "program_name": "Broken rule",
                "origin_airports": "BUR",
                "destination_airports": "",
                "outbound_weekday": "Monday",
                "outbound_time_start": "06:00",
                "outbound_time_end": "10:00",
                "fare_preference": "flexible",
                "lookahead_weeks": "8",
                "rebook_alert_threshold": "20",
            }
        )
