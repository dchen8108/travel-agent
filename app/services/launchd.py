from __future__ import annotations

import getpass
import os
import plistlib
from pathlib import Path


LAUNCH_AGENT_LABEL = "com.travel-agent.fetch-google-flights"


def launch_agent_plist_path() -> Path:
    return Path.home() / "Library" / "LaunchAgents" / f"{LAUNCH_AGENT_LABEL}.plist"


def build_launch_agent_plist(
    *,
    uv_executable: str,
    project_root: Path,
    stdout_log_path: Path,
    stderr_log_path: Path,
    start_interval_seconds: int = 60,
    max_targets: int = 1,
) -> bytes:
    plist = {
        "Label": LAUNCH_AGENT_LABEL,
        "ProgramArguments": [
            uv_executable,
            "run",
            "python",
            "-m",
            "app.jobs.fetch_google_flights",
            "--max-targets",
            str(max_targets),
            "--no-sleep",
        ],
        "WorkingDirectory": str(project_root),
        "RunAtLoad": True,
        "StartInterval": start_interval_seconds,
        "ProcessType": "Background",
        "StandardOutPath": str(stdout_log_path),
        "StandardErrorPath": str(stderr_log_path),
        "EnvironmentVariables": {
            "PYTHONUNBUFFERED": "1",
        },
    }
    return plistlib.dumps(plist, fmt=plistlib.FMT_XML, sort_keys=False)


def launch_agent_domain() -> str:
    return f"gui/{os.getuid()}"


def launch_agent_target() -> str:
    return f"{launch_agent_domain()}/{LAUNCH_AGENT_LABEL}"


def default_log_paths(project_root: Path) -> tuple[Path, Path]:
    logs_dir = project_root / "data" / "logs"
    return (
        logs_dir / "fetch_google_flights.stdout.log",
        logs_dir / "fetch_google_flights.stderr.log",
    )


def installation_summary(*, plist_path: Path, interval_seconds: int, max_targets: int) -> str:
    return (
        f"Installed {LAUNCH_AGENT_LABEL} for {getpass.getuser()} at {plist_path} "
        f"(runs every {interval_seconds}s, max_targets={max_targets})."
    )
