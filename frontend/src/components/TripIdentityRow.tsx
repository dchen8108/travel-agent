import { useQueryClient } from "@tanstack/react-query";

import type { TripIdentity } from "../types";
import { prefetchTripEditorFromHref } from "../lib/tripEditorPrefetch";
import { DeleteIcon, EditIcon } from "./Icons";
import { IconButton } from "./IconButton";
import { PrefetchLink } from "./PrefetchLink";

interface Props {
  trip: TripIdentity;
  onDelete?: () => void;
}

export function TripIdentityRow({ trip, onDelete }: Props) {
  const queryClient = useQueryClient();

  return (
    <div className="trip-identity-row">
      <div className="date-tile">
        <span className="date-tile__weekday">{trip.dateTile.weekday}</span>
        <span className="date-tile__month-day">{trip.dateTile.monthDay}</span>
      </div>
      <div className="trip-identity-row__copy">
        <h3>{trip.title}</h3>
      </div>
      <div className="trip-identity-row__actions">
        <PrefetchLink
          className="icon-link"
          to={trip.editHref}
          aria-label="Edit trip"
          title="Edit trip"
          onPrefetch={() => void prefetchTripEditorFromHref(queryClient, trip.editHref)}
        >
          <EditIcon />
        </PrefetchLink>
        {trip.delete && onDelete ? (
          <IconButton label={trip.delete.confirmation.action} tone="danger" onClick={onDelete}>
            <DeleteIcon />
          </IconButton>
        ) : null}
      </div>
    </div>
  );
}
