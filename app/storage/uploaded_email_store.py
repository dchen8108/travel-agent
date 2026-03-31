from __future__ import annotations

import os
from pathlib import Path
import tempfile

from app.storage.file_lock import locked_file


def persist_uploaded_email(destination_dir: Path, email_event_id: str, payload: bytes) -> Path:
    destination_dir.mkdir(parents=True, exist_ok=True)
    path = destination_dir / f"{email_event_id}.eml"
    lock_path = destination_dir / ".emails.lock"
    with locked_file(lock_path):
        with tempfile.NamedTemporaryFile("wb", dir=destination_dir, delete=False) as handle:
            handle.write(payload)
            temp_path = Path(handle.name)
        os.replace(temp_path, path)
    return path
