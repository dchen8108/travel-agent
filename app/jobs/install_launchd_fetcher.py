from __future__ import annotations

import argparse
import shutil
import subprocess
from pathlib import Path

from app.storage.repository import Repository
from app.services.launchd import (
    FETCH_LAUNCH_AGENT_LABEL,
    build_launch_agent_plist,
    default_log_paths,
    installation_summary,
    launch_agent_domain,
    launch_agent_plist_path,
    launch_agent_target,
)
from app.settings import get_settings


def _bootout_if_loaded(plist_path: Path) -> None:
    subprocess.run(
        ["launchctl", "bootout", launch_agent_domain(), str(plist_path)],
        check=False,
        capture_output=True,
        text=True,
    )


def main() -> None:
    settings = get_settings()
    app_state = Repository(settings).load_app_state()
    parser = argparse.ArgumentParser()
    parser.add_argument("--interval-seconds", type=int, default=app_state.launchd_fetch_interval_seconds)
    parser.add_argument("--max-targets", type=int, default=app_state.launchd_fetch_max_targets)
    args = parser.parse_args()

    project_root = settings.project_root
    uv_executable = shutil.which("uv")
    if not uv_executable:
        raise SystemExit("Could not find `uv` in PATH.")

    stdout_log_path, stderr_log_path = default_log_paths(project_root, "fetch_google_flights")
    stdout_log_path.parent.mkdir(parents=True, exist_ok=True)
    plist_path = launch_agent_plist_path(FETCH_LAUNCH_AGENT_LABEL)
    plist_path.parent.mkdir(parents=True, exist_ok=True)

    plist_payload = build_launch_agent_plist(
        uv_executable=uv_executable,
        project_root=project_root,
        stdout_log_path=stdout_log_path,
        stderr_log_path=stderr_log_path,
        start_interval_seconds=args.interval_seconds,
        max_targets=args.max_targets,
    )

    _bootout_if_loaded(plist_path)
    plist_path.write_bytes(plist_payload)
    subprocess.run(
        ["launchctl", "bootstrap", launch_agent_domain(), str(plist_path)],
        check=True,
    )
    subprocess.run(
        ["launchctl", "kickstart", "-k", launch_agent_target()],
        check=True,
    )
    print(
        installation_summary(
            label=FETCH_LAUNCH_AGENT_LABEL,
            plist_path=plist_path,
            interval_seconds=args.interval_seconds,
            extra_summary=f"max_targets={args.max_targets}",
        )
    )
    print(f"Logs: {stdout_log_path} and {stderr_log_path}")


if __name__ == "__main__":
    main()
