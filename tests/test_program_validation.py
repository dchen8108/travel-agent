from __future__ import annotations

import pytest

from app.route_details import parse_route_detail_rankings
from app.services.programs import ProgramValidationError, build_program


def test_build_program_normalizes_legacy_airline_case_into_route_details() -> None:
    program = build_program(
        {
            "program_id": "draft",
            "program_name": "Legacy rule",
            "origin_airports": "BUR",
            "destination_airports": "SFO",
            "outbound_weekday": "Monday",
            "outbound_time_start": "06:00",
            "outbound_time_end": "10:00",
            "preferred_airlines": "ALASKA|UNITED",
            "allowed_airlines": "ALASKA|UNITED|DELTA",
            "nonstop_only": "true",
        }
    )

    details = parse_route_detail_rankings(program.route_detail_rankings)

    assert [detail.airline for detail in details] == ["Alaska", "United", "Delta"]


def test_build_program_requires_at_least_one_ranked_route_detail() -> None:
    with pytest.raises(ProgramValidationError):
        build_program(
            {
                "program_id": "draft",
                "program_name": "Broken rule",
                "route_detail_rankings": "[]",
            }
        )


def test_build_program_rejects_invalid_route_detail_values() -> None:
    with pytest.raises(ProgramValidationError):
        build_program(
            {
                "program_id": "draft",
                "program_name": "Broken rule",
                "route_detail_rankings": '[{"origin_airport":"XXX","destination_airport":"SFO","weekday":"Monday","start_time":"06:00","end_time":"10:00","airline":"Alaska","nonstop_only":true}]',
            }
        )


def test_build_program_rejects_duplicate_route_details() -> None:
    duplicate_details = '[{"origin_airport":"BUR","destination_airport":"SFO","weekday":"Monday","start_time":"06:00","end_time":"10:00","airline":"Alaska","nonstop_only":true},{"origin_airport":"BUR","destination_airport":"SFO","weekday":"Monday","start_time":"06:00","end_time":"10:00","airline":"Alaska","nonstop_only":true}]'
    with pytest.raises(ProgramValidationError):
        build_program(
            {
                "program_id": "draft",
                "program_name": "Duplicate rule",
                "route_detail_rankings": duplicate_details,
            }
        )
