from __future__ import annotations

import subprocess

from app.services.launchd import launch_agent_domain, launch_agent_plist_path


def main() -> None:
    plist_path = launch_agent_plist_path()
    subprocess.run(
        ["launchctl", "bootout", launch_agent_domain(), str(plist_path)],
        check=False,
    )
    if plist_path.exists():
        plist_path.unlink()
    print(f"Removed launch agent at {plist_path}")


if __name__ == "__main__":
    main()
