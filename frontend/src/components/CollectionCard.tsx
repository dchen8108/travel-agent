import type { CollectionCard as CollectionCardValue } from "../types";
import { EditIcon } from "./Icons";
import { IconButton } from "./IconButton";

interface Props {
  collection: CollectionCardValue;
  onEdit: () => void;
  onToggleRecurringTrip: (tripId: string, active: boolean) => void;
}

export function CollectionCard({ collection, onEdit, onToggleRecurringTrip }: Props) {
  return (
    <article className="collection-card" id={`group-${collection.groupId}`}>
      <div className="collection-card__header">
        <div className="collection-card__titleline">
          <h3>{collection.label}</h3>
          <IconButton label="Edit collection" onClick={onEdit}>
            <EditIcon />
          </IconButton>
        </div>
        <a className="primary-button" href={collection.createTripHref}>Create trip</a>
      </div>
      {collection.recurringTrips.length > 0 ? (
        <div className="recurring-grid">
          {collection.recurringTrips.map((trip) => (
            <article className="recurring-card" key={trip.tripId}>
              <div className="recurring-card__copy">
                <div className="recurring-card__titleline">
                  <strong>{trip.label}</strong>
                  <a className="icon-link" href={trip.editHref} aria-label="Edit recurring trip" title="Edit recurring trip">
                    <EditIcon />
                  </a>
                </div>
                <p>Repeats on {trip.anchorWeekday}</p>
              </div>
              <button
                type="button"
                className={`status-toggle ${trip.active ? "is-active" : ""}`}
                onClick={() => onToggleRecurringTrip(trip.tripId, !trip.active)}
              >
                <span>{trip.active ? "Active" : "Paused"}</span>
              </button>
            </article>
          ))}
        </div>
      ) : null}
      <div className="pill-row">
        {collection.upcomingTrips.length > 0 ? (
          collection.upcomingTrips.map((trip) => (
            <a key={`${collection.groupId}-${trip.label}`} className={`trip-pill trip-pill--${trip.tone}`} href={trip.href} title={trip.title}>
              {trip.label}
            </a>
          ))
        ) : (
          <p className="empty-copy">No trips yet.</p>
        )}
      </div>
    </article>
  );
}
