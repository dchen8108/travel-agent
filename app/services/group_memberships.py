from __future__ import annotations

from collections import defaultdict

from app.models.base import DataScope, TripInstanceInheritanceMode, TripKind, utcnow
from app.models.rule_group_target import RuleGroupTarget
from app.models.trip import Trip
from app.models.trip_instance import TripInstance
from app.models.trip_instance_group_membership import TripInstanceGroupMembership
from app.storage.repository import Repository


def rule_group_ids(rule_group_targets: list[RuleGroupTarget], rule_trip_id: str) -> list[str]:
    return sorted(
        {
            target.trip_group_id
            for target in rule_group_targets
            if target.rule_trip_id == rule_trip_id
        }
    )


def build_rule_group_targets(
    *,
    rule_trip_id: str,
    trip_group_ids: list[str],
    data_scope: str | DataScope,
    existing_targets: list[RuleGroupTarget] | None = None,
) -> list[RuleGroupTarget]:
    existing_by_group_id = {target.trip_group_id: target for target in existing_targets or []}
    now = utcnow()
    unique_group_ids = sorted({group_id for group_id in trip_group_ids if group_id})
    return [
        RuleGroupTarget(
            rule_trip_id=rule_trip_id,
            trip_group_id=trip_group_id,
            data_scope=DataScope(str(data_scope or DataScope.LIVE)),
            created_at=existing_by_group_id.get(trip_group_id, RuleGroupTarget(rule_trip_id=rule_trip_id, trip_group_id=trip_group_id)).created_at,
            updated_at=now,
        )
        for trip_group_id in unique_group_ids
    ]


def replace_manual_trip_instance_groups(
    repository: Repository,
    *,
    trip_instance_ids: list[str],
    trip_group_ids: list[str],
    data_scope: str | DataScope,
    membership_source: str = "manual",
    source_rule_trip_id: str = "",
) -> None:
    unique_group_ids = sorted({trip_group_id for trip_group_id in trip_group_ids if trip_group_id})
    now = utcnow()
    existing_memberships = repository.load_trip_instance_group_memberships()
    existing_by_key = {
        (membership.trip_instance_id, membership.trip_group_id): membership
        for membership in existing_memberships
    }
    for trip_instance_id in trip_instance_ids:
        memberships = []
        for trip_group_id in unique_group_ids:
            existing = existing_by_key.get((trip_instance_id, trip_group_id))
            memberships.append(
                TripInstanceGroupMembership(
                    trip_instance_id=trip_instance_id,
                    trip_group_id=trip_group_id,
                    membership_source=membership_source,
                    source_rule_trip_id=source_rule_trip_id,
                    data_scope=DataScope(str(data_scope or DataScope.LIVE)),
                    created_at=existing.created_at if existing else now,
                    updated_at=now,
                )
            )
        repository.replace_trip_instance_group_memberships_for_instance(trip_instance_id, memberships)


def reconcile_trip_instance_group_memberships(
    *,
    trips: list[Trip],
    rule_group_targets: list[RuleGroupTarget],
    trip_instances: list[TripInstance],
    existing_memberships: list[TripInstanceGroupMembership],
) -> list[TripInstanceGroupMembership]:
    trip_by_id = {trip.trip_id: trip for trip in trips}
    rule_group_ids_by_rule_id: dict[str, list[str]] = defaultdict(list)
    for target in rule_group_targets:
        rule_group_ids_by_rule_id[target.rule_trip_id].append(target.trip_group_id)

    existing_by_instance_id: dict[str, list[TripInstanceGroupMembership]] = defaultdict(list)
    for membership in existing_memberships:
        existing_by_instance_id[membership.trip_instance_id].append(membership)

    reconciled: list[TripInstanceGroupMembership] = []
    for trip_instance in trip_instances:
        existing_by_group_id = {
            membership.trip_group_id: membership
            for membership in existing_by_instance_id.get(trip_instance.trip_instance_id, [])
        }
        if trip_instance.deleted:
            for membership in existing_by_group_id.values():
                membership.data_scope = trip_instance.data_scope
                membership.updated_at = utcnow()
                reconciled.append(membership)
            continue

        if (
            trip_instance.inheritance_mode == TripInstanceInheritanceMode.ATTACHED
            and trip_instance.recurring_rule_trip_id
            and (
                rule_trip := trip_by_id.get(trip_instance.recurring_rule_trip_id)
            ) is not None
            and rule_trip.trip_kind == TripKind.WEEKLY
        ):
            now = utcnow()
            for trip_group_id in sorted(set(rule_group_ids_by_rule_id.get(trip_instance.recurring_rule_trip_id, []))):
                existing = existing_by_group_id.get(trip_group_id)
                reconciled.append(
                    TripInstanceGroupMembership(
                        trip_instance_id=trip_instance.trip_instance_id,
                        trip_group_id=trip_group_id,
                        membership_source="inherited",
                        source_rule_trip_id=trip_instance.recurring_rule_trip_id,
                        data_scope=trip_instance.data_scope,
                        created_at=existing.created_at if existing else now,
                        updated_at=now,
                    )
                )
            continue

        for membership in existing_by_group_id.values():
            membership.data_scope = trip_instance.data_scope
            if trip_instance.inheritance_mode == TripInstanceInheritanceMode.DETACHED and membership.membership_source == "inherited":
                membership.membership_source = "frozen"
                membership.source_rule_trip_id = trip_instance.recurring_rule_trip_id
            elif trip_instance.inheritance_mode != TripInstanceInheritanceMode.DETACHED:
                membership.membership_source = "manual"
                membership.source_rule_trip_id = ""
            membership.updated_at = utcnow()
            reconciled.append(membership)

    reconciled.sort(key=lambda membership: (membership.trip_group_id, membership.trip_instance_id))
    return reconciled
