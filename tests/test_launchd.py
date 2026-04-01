from __future__ import annotations

import plistlib
from pathlib import Path

from app.services.launchd import LAUNCH_AGENT_LABEL, build_launch_agent_plist


def test_launch_agent_plist_contains_expected_program_arguments() -> None:
    payload = build_launch_agent_plist(
        uv_executable="/usr/local/bin/uv",
        project_root=Path("/Users/example/code/travel-agent"),
        stdout_log_path=Path("/Users/example/code/travel-agent/data/logs/fetch.stdout.log"),
        stderr_log_path=Path("/Users/example/code/travel-agent/data/logs/fetch.stderr.log"),
        start_interval_seconds=60,
        max_targets=2,
    )

    plist = plistlib.loads(payload)

    assert plist["Label"] == LAUNCH_AGENT_LABEL
    assert plist["ProgramArguments"] == [
        "/usr/local/bin/uv",
        "run",
        "python",
        "-m",
        "app.jobs.fetch_google_flights",
        "--max-targets",
        "2",
    ]
    assert plist["WorkingDirectory"] == "/Users/example/code/travel-agent"
    assert plist["RunAtLoad"] is True
    assert plist["StartInterval"] == 60
