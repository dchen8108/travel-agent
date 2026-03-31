from __future__ import annotations

import argparse
from pathlib import Path

from app.services.email_import import import_email_payload
from app.settings import get_settings
from app.storage.repository import Repository


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("path", type=Path)
    args = parser.parse_args()

    repository = Repository(get_settings())
    event = import_email_payload(repository, args.path.name, args.path.read_bytes())
    print(f"Imported {event.email_event_id} with status {event.parsed_status}")


if __name__ == "__main__":
    main()
