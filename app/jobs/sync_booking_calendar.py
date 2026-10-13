from __future__ import annotations

import argparse
import json
import sys

from app.models.base import utcnow
from app.services.booking_calendar_sync import sync_booking_calendar
from app.settings import get_settings
from app.storage.repository import Repository


def _emit_log(event: str, *, stream=sys.stdout, **fields: object) -> None:
    payload = {
        "timestamp": utcnow().isoformat(),
        "event": event,
        **fields,
    }
    print(json.dumps(payload, sort_keys=True, default=str), file=stream, flush=True)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--json", action="store_true", help="Print only the machine-readable sync result.")
    args = parser.parse_args()

    repository = Repository(get_settings())
    result = sync_booking_calendar(repository, verify_remote=True)
    payload = result.__dict__
    if args.json:
        print(json.dumps(payload, sort_keys=True, default=str))
        return
    _emit_log("booking_calendar_sync_completed", **payload)


if __name__ == "__main__":
    main()
