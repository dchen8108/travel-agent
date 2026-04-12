from __future__ import annotations

from app.models.base import DataScope, utcnow
from app.models.trip_group import TripGroup
from app.services.ids import new_id
from app.storage.repository import Repository


def normalize_group_label(label: str) -> str:
    return label.strip().lower()


def find_trip_group_by_label(
    trip_groups: list[TripGroup],
    label: str,
) -> TripGroup | None:
    normalized = normalize_group_label(label)
    return next(
        (trip_group for trip_group in trip_groups if normalize_group_label(trip_group.label) == normalized),
        None,
    )


def ensure_unique_group_label(
    trip_groups: list[TripGroup],
    label: str,
    *,
    existing_trip_group_id: str | None = None,
) -> None:
    normalized = normalize_group_label(label)
    for trip_group in trip_groups:
        if existing_trip_group_id and trip_group.trip_group_id == existing_trip_group_id:
            continue
        if normalize_group_label(trip_group.label) == normalized:
            raise ValueError("Group names must be unique.")


def build_trip_group(
    *,
    trip_group_id: str | None,
    label: str,
    data_scope: str = DataScope.LIVE,
) -> TripGroup:
    now = utcnow()
    return TripGroup(
        trip_group_id=trip_group_id or new_id("grp"),
        label=label,
        data_scope=DataScope(data_scope),
        created_at=now,
        updated_at=now,
    )


def save_trip_group(
    repository: Repository,
    *,
    trip_group_id: str | None,
    label: str,
    data_scope: str = DataScope.LIVE,
) -> TripGroup:
    trip_groups = repository.load_trip_groups()
    ensure_unique_group_label(trip_groups, label, existing_trip_group_id=trip_group_id)
    existing = next((item for item in trip_groups if item.trip_group_id == trip_group_id), None) if trip_group_id else None
    if trip_group_id and existing is None:
        raise ValueError("Trip group not found.")
    trip_group = build_trip_group(
        trip_group_id=trip_group_id,
        label=label,
        data_scope=data_scope,
    )
    if existing:
        trip_group.created_at = existing.created_at
        trip_group.updated_at = utcnow()
    repository.upsert_trip_group(trip_group)
    return trip_group


def find_or_create_trip_group(
    repository: Repository,
    *,
    label: str,
    data_scope: str = DataScope.LIVE,
) -> TripGroup:
    trip_groups = repository.load_trip_groups()
    existing = find_trip_group_by_label(trip_groups, label)
    if existing is not None:
        return existing
    return save_trip_group(
        repository,
        trip_group_id=None,
        label=label,
        data_scope=data_scope,
    )


def delete_trip_group(
    repository: Repository,
    *,
    trip_group_id: str,
) -> TripGroup:
    trip_groups = repository.load_trip_groups()
    group = next((item for item in trip_groups if item.trip_group_id == trip_group_id), None)
    if group is None:
        raise KeyError("Trip group not found")
    if any(target.trip_group_id == trip_group_id for target in repository.load_rule_group_targets()):
        raise ValueError("Remove or retarget recurring rules before deleting this group.")

    with repository.transaction():
        repository.delete_trip_instance_group_memberships_by_group_id(trip_group_id)
        repository.delete_trip_group_by_id(trip_group_id)
    return group
