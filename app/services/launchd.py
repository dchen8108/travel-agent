from __future__ import annotations

import getpass
import os
import plistlib
from pathlib import Path


FETCH_LAUNCH_AGENT_LABEL = "com.travel-agent.fetch-google-flights"
BOOKING_POLLER_LAUNCH_AGENT_LABEL = "com.travel-agent.poll-gmail-bookings"
LAUNCH_AGENT_LABEL = FETCH_LAUNCH_AGENT_LABEL


def launch_agent_plist_path(label: str = FETCH_LAUNCH_AGENT_LABEL) -> Path:
    return Path.home() / "Library" / "LaunchAgents" / f"{label}.plist"


def build_job_launch_agent_plist(
    *,
    label: str,
    uv_executable: str,
    project_root: Path,
    module_name: str,
    stdout_log_path: Path,
    stderr_log_path: Path,
    start_interval_seconds: int,
    module_args: list[str] | None = None,
) -> bytes:
    plist = {
        "Label": label,
        "ProgramArguments": [
            uv_executable,
            "run",
            "python",
            "-m",
            module_name,
            *(module_args or []),
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


def build_launch_agent_plist(
    *,
    uv_executable: str,
    project_root: Path,
    stdout_log_path: Path,
    stderr_log_path: Path,
    start_interval_seconds: int,
    max_targets: int,
) -> bytes:
    return build_job_launch_agent_plist(
        label=FETCH_LAUNCH_AGENT_LABEL,
        uv_executable=uv_executable,
        project_root=project_root,
        module_name="app.jobs.fetch_google_flights",
        stdout_log_path=stdout_log_path,
        stderr_log_path=stderr_log_path,
        start_interval_seconds=start_interval_seconds,
        module_args=["--max-targets", str(max_targets)],
    )


def build_booking_poller_launch_agent_plist(
    *,
    uv_executable: str,
    project_root: Path,
    stdout_log_path: Path,
    stderr_log_path: Path,
    start_interval_seconds: int,
    max_messages: int,
) -> bytes:
    return build_job_launch_agent_plist(
        label=BOOKING_POLLER_LAUNCH_AGENT_LABEL,
        uv_executable=uv_executable,
        project_root=project_root,
        module_name="app.jobs.poll_gmail_bookings",
        stdout_log_path=stdout_log_path,
        stderr_log_path=stderr_log_path,
        start_interval_seconds=start_interval_seconds,
        module_args=["--max-messages", str(max_messages)],
    )


def launch_agent_domain() -> str:
    return f"gui/{os.getuid()}"


def launch_agent_target(label: str = FETCH_LAUNCH_AGENT_LABEL) -> str:
    return f"{launch_agent_domain()}/{label}"


def default_log_paths(project_root: Path, stem: str = "fetch_google_flights") -> tuple[Path, Path]:
    logs_dir = project_root / "data" / "logs"
    return (
        logs_dir / f"{stem}.stdout.log",
        logs_dir / f"{stem}.stderr.log",
    )


def installation_summary(*, label: str, plist_path: Path, interval_seconds: int, extra_summary: str) -> str:
    return (
        f"Installed {label} for {getpass.getuser()} at {plist_path} "
        f"(runs every {interval_seconds}s, {extra_summary})."
    )
