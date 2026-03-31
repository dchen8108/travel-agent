from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from app.models.base import AppState
from app.models.booking import Booking
from app.models.email_event import EmailEvent
from app.models.fare_observation import FareObservation
from app.models.route_option import RouteOption
from app.models.tracker import Tracker
from app.models.trip import Trip
from app.models.trip_instance import TripInstance
from app.models.unmatched_booking import UnmatchedBooking
from app.settings import Settings
from app.storage.csv_store import load_csv_models, save_csv_models
from app.storage.json_store import load_json_model, save_json_model


def _fieldnames(model_type: type) -> list[str]:
    return list(model_type.model_fields.keys())


@dataclass
class Repository:
    settings: Settings

    def _path(self, name: str) -> Path:
        return self.settings.data_dir / name

    def ensure_data_dir(self) -> None:
        self.settings.data_dir.mkdir(parents=True, exist_ok=True)
        self.settings.imported_email_dir.mkdir(parents=True, exist_ok=True)
        if not self._path("app.json").exists():
            self.save_app_state(AppState())
        for name, model_type in (
            ("trips.csv", Trip),
            ("route_options.csv", RouteOption),
            ("trip_instances.csv", TripInstance),
            ("trackers.csv", Tracker),
            ("bookings.csv", Booking),
            ("unmatched_bookings.csv", UnmatchedBooking),
            ("email_events.csv", EmailEvent),
            ("fare_observations.csv", FareObservation),
        ):
            path = self._path(name)
            if not path.exists():
                save_csv_models(path, [], _fieldnames(model_type))

    def load_app_state(self) -> AppState:
        return load_json_model(self._path("app.json"), AppState, AppState())

    def save_app_state(self, app_state: AppState) -> None:
        save_json_model(self._path("app.json"), app_state)

    def load_trips(self) -> list[Trip]:
        return load_csv_models(self._path("trips.csv"), Trip)

    def save_trips(self, trips: list[Trip]) -> None:
        save_csv_models(self._path("trips.csv"), trips, _fieldnames(Trip))

    def load_route_options(self) -> list[RouteOption]:
        return load_csv_models(self._path("route_options.csv"), RouteOption)

    def save_route_options(self, route_options: list[RouteOption]) -> None:
        save_csv_models(self._path("route_options.csv"), route_options, _fieldnames(RouteOption))

    def load_trip_instances(self) -> list[TripInstance]:
        return load_csv_models(self._path("trip_instances.csv"), TripInstance)

    def save_trip_instances(self, trip_instances: list[TripInstance]) -> None:
        save_csv_models(self._path("trip_instances.csv"), trip_instances, _fieldnames(TripInstance))

    def load_trackers(self) -> list[Tracker]:
        return load_csv_models(self._path("trackers.csv"), Tracker)

    def save_trackers(self, trackers: list[Tracker]) -> None:
        save_csv_models(self._path("trackers.csv"), trackers, _fieldnames(Tracker))

    def load_bookings(self) -> list[Booking]:
        return load_csv_models(self._path("bookings.csv"), Booking)

    def save_bookings(self, bookings: list[Booking]) -> None:
        save_csv_models(self._path("bookings.csv"), bookings, _fieldnames(Booking))

    def load_unmatched_bookings(self) -> list[UnmatchedBooking]:
        return load_csv_models(self._path("unmatched_bookings.csv"), UnmatchedBooking)

    def save_unmatched_bookings(self, unmatched_bookings: list[UnmatchedBooking]) -> None:
        save_csv_models(
            self._path("unmatched_bookings.csv"),
            unmatched_bookings,
            _fieldnames(UnmatchedBooking),
        )

    def load_email_events(self) -> list[EmailEvent]:
        return load_csv_models(self._path("email_events.csv"), EmailEvent)

    def save_email_events(self, events: list[EmailEvent]) -> None:
        save_csv_models(self._path("email_events.csv"), events, _fieldnames(EmailEvent))

    def load_fare_observations(self) -> list[FareObservation]:
        return load_csv_models(self._path("fare_observations.csv"), FareObservation)

    def save_fare_observations(self, observations: list[FareObservation]) -> None:
        save_csv_models(
            self._path("fare_observations.csv"),
            observations,
            _fieldnames(FareObservation),
        )
