from __future__ import annotations

from typing import Any

from app.models.booking import Booking


class BookingsRepositoryMixin:
    def load_bookings(self) -> list[Booking]:
        query = """
            SELECT
                booking_id,
                source,
                COALESCE(trip_instance_id, '') AS trip_instance_id,
                COALESCE(route_option_id, '') AS route_option_id,
                data_scope,
                airline,
                origin_airport,
                destination_airport,
                departure_date,
                departure_time,
                arrival_time,
                fare_class,
                flight_number,
                booked_price,
                record_locator,
                booked_at,
                booking_status AS status,
                match_status,
                raw_summary,
                candidate_trip_instance_ids,
                auto_link_enabled,
                resolution_status,
                notes,
                created_at,
                updated_at
            FROM bookings
            WHERE match_status = 'matched'
            ORDER BY rowid
        """
        return self._load_models(query, Booking)

    def replace_bookings(self, bookings: list[Booking]) -> None:
        rows = [self._booking_row(booking) for booking in bookings]
        self._replace_table("bookings", rows, where_sql="match_status = 'matched'")

    def upsert_bookings(self, bookings: list[Booking]) -> None:
        rows = [self._booking_row(booking) for booking in bookings]
        self._upsert_table("bookings", rows, conflict_columns=("booking_id",))

    def delete_bookings_by_ids(self, booking_ids: list[str]) -> None:
        if not booking_ids:
            return
        placeholders = ", ".join(["?"] * len(booking_ids))
        self._delete_from_table(
            "bookings",
            where_sql=f"booking_id IN ({placeholders}) AND match_status = 'matched'",
            where_params=tuple(booking_ids),
        )

    def load_unmatched_bookings(self) -> list[Booking]:
        query = """
            SELECT
                booking_id,
                source,
                COALESCE(trip_instance_id, '') AS trip_instance_id,
                COALESCE(route_option_id, '') AS route_option_id,
                data_scope,
                airline,
                origin_airport,
                destination_airport,
                departure_date,
                departure_time,
                arrival_time,
                fare_class,
                flight_number,
                booked_price,
                record_locator,
                booked_at,
                booking_status AS status,
                match_status,
                raw_summary,
                candidate_trip_instance_ids,
                auto_link_enabled,
                resolution_status,
                notes,
                created_at,
                updated_at
            FROM bookings
            WHERE match_status = 'unmatched'
            ORDER BY rowid
        """
        return self._load_models(query, Booking)

    def replace_unmatched_bookings(self, unmatched_bookings: list[Booking]) -> None:
        rows = [self._booking_row(unmatched) for unmatched in unmatched_bookings]
        self._replace_table("bookings", rows, where_sql="match_status = 'unmatched'")

    def upsert_unmatched_bookings(self, unmatched_bookings: list[Booking]) -> None:
        rows = [self._booking_row(unmatched) for unmatched in unmatched_bookings]
        self._upsert_table("bookings", rows, conflict_columns=("booking_id",))

    def delete_unmatched_bookings_by_ids(self, unmatched_booking_ids: list[str]) -> None:
        if not unmatched_booking_ids:
            return
        placeholders = ", ".join(["?"] * len(unmatched_booking_ids))
        self._delete_from_table(
            "bookings",
            where_sql=f"booking_id IN ({placeholders}) AND match_status = 'unmatched'",
            where_params=tuple(unmatched_booking_ids),
        )

    @staticmethod
    def _booking_row(booking: Booking) -> dict[str, Any]:
        return {
            "booking_id": booking.booking_id,
            "source": booking.source,
            "trip_instance_id": booking.trip_instance_id or None,
            "route_option_id": booking.route_option_id,
            "data_scope": booking.data_scope,
            "airline": booking.airline,
            "origin_airport": booking.origin_airport,
            "destination_airport": booking.destination_airport,
            "departure_date": booking.departure_date.isoformat(),
            "departure_time": booking.departure_time,
            "arrival_time": booking.arrival_time,
            "fare_class": booking.fare_class,
            "flight_number": booking.flight_number,
            "booked_price": float(booking.booked_price),
            "record_locator": booking.record_locator,
            "booked_at": booking.booked_at.isoformat(),
            "booking_status": booking.status,
            "match_status": booking.match_status,
            "raw_summary": booking.raw_summary,
            "candidate_trip_instance_ids": booking.candidate_trip_instance_ids,
            "auto_link_enabled": booking.auto_link_enabled,
            "resolution_status": booking.resolution_status,
            "notes": booking.notes,
            "created_at": booking.created_at.isoformat(),
            "updated_at": booking.updated_at.isoformat(),
        }
