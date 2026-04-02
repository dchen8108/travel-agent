from __future__ import annotations

from app.models.base import AppState, DataScope
from app.services.snapshots import AppSnapshot


def include_test_data_for_ui(app_state: AppState) -> bool:
    return bool(app_state.show_test_data)


def include_test_data_for_processing(app_state: AppState) -> bool:
    return bool(app_state.process_test_data)


def item_scope(item: object) -> str:
    return str(getattr(item, "data_scope", DataScope.LIVE))


def include_item(item: object, *, include_test_data: bool) -> bool:
    return include_test_data or item_scope(item) != DataScope.TEST


def filter_items(items: list[object], *, include_test_data: bool):
    if include_test_data:
        return list(items)
    return [item for item in items if include_item(item, include_test_data=False)]


def filter_snapshot(snapshot: AppSnapshot, *, include_test_data: bool) -> AppSnapshot:
    if include_test_data:
        return snapshot
    return AppSnapshot(
        trips=filter_items(snapshot.trips, include_test_data=False),
        route_options=filter_items(snapshot.route_options, include_test_data=False),
        trip_instances=filter_items(snapshot.trip_instances, include_test_data=False),
        trackers=filter_items(snapshot.trackers, include_test_data=False),
        tracker_fetch_targets=filter_items(snapshot.tracker_fetch_targets, include_test_data=False),
        bookings=filter_items(snapshot.bookings, include_test_data=False),
        unmatched_bookings=filter_items(snapshot.unmatched_bookings, include_test_data=False),
        booking_email_events=filter_items(snapshot.booking_email_events, include_test_data=False),
        price_records=filter_items(snapshot.price_records, include_test_data=False),
        app_state=snapshot.app_state,
    )
