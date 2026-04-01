from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from app.models.base import AppState
from app.models.booking import Booking
from app.models.price_record import PriceRecord
from app.models.route_option import RouteOption
from app.models.tracker import Tracker
from app.models.tracker_fetch_target import TrackerFetchTarget
from app.models.trip import Trip
from app.models.trip_instance import TripInstance
from app.models.unmatched_booking import UnmatchedBooking
from app.settings import Settings
from app.storage.csv_store import append_csv_models, load_csv_models, save_csv_models
from app.storage.json_store import load_json_model, save_json_model


def _fieldnames(model_type: type) -> list[str]:
    return list(model_type.model_fields.keys())


CSV_MODELS: tuple[tuple[str, type], ...] = (
    ("trips.csv", Trip),
    ("route_options.csv", RouteOption),
    ("trip_instances.csv", TripInstance),
    ("trackers.csv", Tracker),
    ("tracker_fetch_targets.csv", TrackerFetchTarget),
    ("bookings.csv", Booking),
    ("unmatched_bookings.csv", UnmatchedBooking),
    ("price_records.csv", PriceRecord),
)


@dataclass
class Repository:
    settings: Settings

    def _path(self, name: str) -> Path:
        return self.settings.data_dir / name

    def ensure_data_dir(self) -> None:
        self.settings.data_dir.mkdir(parents=True, exist_ok=True)
        if not self._path("app.json").exists():
            self.save_app_state(AppState())
        for name, model_type in CSV_MODELS:
            path = self._path(name)
            if not path.exists():
                save_csv_models(path, [], _fieldnames(model_type))

    def _load_csv(self, filename: str, model_type: type):
        return load_csv_models(self._path(filename), model_type)

    def _save_csv(self, filename: str, rows: list, model_type: type) -> None:
        save_csv_models(self._path(filename), rows, _fieldnames(model_type))

    def load_app_state(self) -> AppState:
        return load_json_model(self._path("app.json"), AppState, AppState())

    def save_app_state(self, app_state: AppState) -> None:
        save_json_model(self._path("app.json"), app_state)

    def load_trips(self) -> list[Trip]:
        return self._load_csv("trips.csv", Trip)

    def save_trips(self, trips: list[Trip]) -> None:
        self._save_csv("trips.csv", trips, Trip)

    def load_route_options(self) -> list[RouteOption]:
        return self._load_csv("route_options.csv", RouteOption)

    def save_route_options(self, route_options: list[RouteOption]) -> None:
        self._save_csv("route_options.csv", route_options, RouteOption)

    def load_trip_instances(self) -> list[TripInstance]:
        return self._load_csv("trip_instances.csv", TripInstance)

    def save_trip_instances(self, trip_instances: list[TripInstance]) -> None:
        self._save_csv("trip_instances.csv", trip_instances, TripInstance)

    def load_trackers(self) -> list[Tracker]:
        return self._load_csv("trackers.csv", Tracker)

    def save_trackers(self, trackers: list[Tracker]) -> None:
        self._save_csv("trackers.csv", trackers, Tracker)

    def load_tracker_fetch_targets(self) -> list[TrackerFetchTarget]:
        return self._load_csv("tracker_fetch_targets.csv", TrackerFetchTarget)

    def save_tracker_fetch_targets(self, targets: list[TrackerFetchTarget]) -> None:
        self._save_csv("tracker_fetch_targets.csv", targets, TrackerFetchTarget)

    def load_bookings(self) -> list[Booking]:
        return self._load_csv("bookings.csv", Booking)

    def save_bookings(self, bookings: list[Booking]) -> None:
        self._save_csv("bookings.csv", bookings, Booking)

    def load_unmatched_bookings(self) -> list[UnmatchedBooking]:
        return self._load_csv("unmatched_bookings.csv", UnmatchedBooking)

    def save_unmatched_bookings(self, unmatched_bookings: list[UnmatchedBooking]) -> None:
        self._save_csv("unmatched_bookings.csv", unmatched_bookings, UnmatchedBooking)

    def load_price_records(self) -> list[PriceRecord]:
        return self._load_csv("price_records.csv", PriceRecord)

    def append_price_records(self, records: list[PriceRecord]) -> None:
        append_csv_models(
            self._path("price_records.csv"),
            records,
            _fieldnames(PriceRecord),
        )
