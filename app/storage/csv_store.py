from __future__ import annotations

import csv
import os
import tempfile
from pathlib import Path
from typing import Iterable, TypeVar

from pydantic import BaseModel

from app.storage.file_lock import locked_file

T = TypeVar("T", bound=BaseModel)


def load_csv_models(path: Path, model_type: type[T]) -> list[T]:
    if not path.exists():
        return []
    with path.open("r", encoding="utf-8", newline="") as handle:
        reader = csv.DictReader(handle)
        return [model_type.model_validate(_normalize_row(row)) for row in reader]


def save_csv_models(path: Path, models: Iterable[T], fieldnames: list[str]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    models = list(models)
    lock_path = path.with_suffix(path.suffix + ".lock")
    with locked_file(lock_path):
        _write_csv_models_unlocked(path, models, fieldnames)


def append_csv_models(path: Path, models: Iterable[T], fieldnames: list[str]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    models = list(models)
    if not models:
        return
    lock_path = path.with_suffix(path.suffix + ".lock")
    with locked_file(lock_path):
        existing_models: list[T] = []
        if path.exists() and path.stat().st_size > 0:
            model_type = type(models[0])
            with path.open("r", encoding="utf-8", newline="") as handle:
                reader = csv.DictReader(handle)
                existing_models = [model_type.model_validate(_normalize_row(row)) for row in reader]
        _write_csv_models_unlocked(path, [*existing_models, *models], fieldnames)


def _normalize_row(row: dict[str, str]) -> dict[str, str | None]:
    return {key: (value if value != "" else None) for key, value in row.items()}


def _write_csv_models_unlocked(path: Path, models: Iterable[T], fieldnames: list[str]) -> None:
    with tempfile.NamedTemporaryFile(
        "w",
        encoding="utf-8",
        newline="",
        dir=path.parent,
        delete=False,
    ) as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        for model in models:
            writer.writerow(model.model_dump(mode="json"))
        temp_path = Path(handle.name)
    os.replace(temp_path, path)
