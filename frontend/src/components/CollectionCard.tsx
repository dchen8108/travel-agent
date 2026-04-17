import { useQueryClient } from "@tanstack/react-query";

import type { CollectionCard as CollectionCardValue } from "../types";
import { prefetchTripEditorFromHref } from "../lib/tripEditorPrefetch";
import { EditIcon } from "./Icons";
import { IconButton } from "./IconButton";
import { PrefetchLink } from "./PrefetchLink";

interface Props {
  collection: CollectionCardValue;
  onEdit: () => void;
  onToggleRecurringTrip: (tripId: string, active: boolean) => void;
  pendingRecurringTripId?: string;
}

export function CollectionCard({ collection, onEdit, onToggleRecurringTrip, pendingRecurringTripId = "" }: Props) {
  const queryClient = useQueryClient();

  return (
    <article className="collection-card" id={`group-${collection.groupId}`}>
      <div className="collection-card__header">
        <div className="collection-card__titleline">
          <h3>{collection.label}</h3>
          <IconButton label="Edit collection" onClick={onEdit}>
            <EditIcon />
          </IconButton>
        </div>
        <PrefetchLink
          className="primary-button"
          to={collection.createTripHref}
          onPrefetch={() => void prefetchTripEditorFromHref(queryClient, collection.createTripHref)}
        >
          Create trip
        </PrefetchLink>
      </div>
      {collection.recurringTrips.length > 0 ? (
        <div className="recurring-grid">
          {collection.recurringTrips.map((trip) => (
            <article className="recurring-card" key={trip.tripId}>
              <div className="recurring-card__copy">
                <div className="recurring-card__titleline">
                  <strong>{trip.label}</strong>
                  <PrefetchLink
                    className="icon-link"
                    to={trip.editHref}
                    aria-label="Edit recurring trip"
                    title="Edit recurring trip"
                    onPrefetch={() => void prefetchTripEditorFromHref(queryClient, trip.editHref)}
                  >
                    <EditIcon />
                  </PrefetchLink>
                </div>
                <p>Repeats on {trip.anchorWeekday}</p>
              </div>
              <button
                type="button"
                className={`status-toggle ${trip.active ? "is-active" : ""}`}
                disabled={pendingRecurringTripId === trip.tripId}
                onClick={() => onToggleRecurringTrip(trip.tripId, !trip.active)}
              >
                <span>{pendingRecurringTripId === trip.tripId ? "Updating…" : trip.active ? "Active" : "Paused"}</span>
              </button>
            </article>
          ))}
        </div>
      ) : null}
      <div className="pill-row">
        {collection.upcomingTrips.length > 0 ? (
          collection.upcomingTrips.map((trip) => (
            <PrefetchLink
              key={trip.tripInstanceId}
              className={`trip-pill trip-pill--${trip.lifecycle}`}
              to={trip.href}
              title={trip.title}
            >
              <span>{trip.label}</span>
              {trip.attentionKind ? (
                <span
                  className={`trip-pill__marker trip-pill__marker--${trip.attentionKind}`}
                  aria-hidden="true"
                />
              ) : null}
            </PrefetchLink>
          ))
        ) : (
          <p className="empty-copy">No trips yet.</p>
        )}
      </div>
    </article>
  );
}
