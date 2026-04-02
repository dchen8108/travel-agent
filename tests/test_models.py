from __future__ import annotations

from pytest import raises

from app.models.trip_instance import TripInstance
from app.models.trip_instance_group_membership import TripInstanceGroupMembership


def test_trip_instance_rejects_standalone_attached_state() -> None:
    with raises(ValueError, match="manual or detached"):
        TripInstance(
            trip_instance_id="inst_bad",
            trip_id="trip_one",
            display_label="Bad instance",
            anchor_date="2026-04-06",
            instance_kind="standalone",
            inheritance_mode="attached",
            recurring_rule_trip_id="trip_rule",
            rule_occurrence_date="2026-04-06",
        )


def test_trip_instance_rejects_generated_instances_without_rule_linkage() -> None:
    with raises(ValueError, match="require recurring rule linkage"):
        TripInstance(
            trip_instance_id="inst_bad",
            trip_id="trip_rule",
            display_label="Bad generated instance",
            anchor_date="2026-04-06",
            instance_kind="generated",
            inheritance_mode="attached",
        )


def test_trip_instance_group_membership_requires_source_rule_for_inherited_rows() -> None:
    with raises(ValueError, match="source rule id"):
        TripInstanceGroupMembership(
            trip_instance_id="inst_1",
            trip_group_id="grp_1",
            membership_source="inherited",
        )


def test_trip_instance_group_membership_rejects_source_rule_for_manual_rows() -> None:
    with raises(ValueError, match="Manual memberships"):
        TripInstanceGroupMembership(
            trip_instance_id="inst_1",
            trip_group_id="grp_1",
            membership_source="manual",
            source_rule_trip_id="trip_rule",
        )
