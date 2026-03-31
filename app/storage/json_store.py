from __future__ import annotations

import json
import os
import tempfile
from pathlib import Path
from typing import TypeVar

from pydantic import BaseModel

from app.storage.file_lock import locked_file

T = TypeVar("T", bound=BaseModel)


def load_json_model(path: Path, model_type: type[T], default: T) -> T:
    if not path.exists():
        return default
    with path.open("r", encoding="utf-8") as handle:
        payload = json.load(handle)
    return model_type.model_validate(payload)


def save_json_model(path: Path, model: BaseModel) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    lock_path = path.with_suffix(path.suffix + ".lock")
    with locked_file(lock_path):
        with tempfile.NamedTemporaryFile(
            "w",
            encoding="utf-8",
            dir=path.parent,
            delete=False,
        ) as handle:
            json.dump(model.model_dump(mode="json"), handle, indent=2, sort_keys=True)
            temp_path = Path(handle.name)
        os.replace(temp_path, path)
