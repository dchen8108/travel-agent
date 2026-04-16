import type { TripIdentity } from "../types";
import { DeleteIcon, EditIcon } from "./Icons";
import { IconButton } from "./IconButton";

interface Props {
  trip: TripIdentity;
  onDelete?: () => void;
}

export function TripIdentityRow({ trip, onDelete }: Props) {
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
        <a className="icon-link" href={trip.editHref} aria-label="Edit trip" title="Edit trip">
          <EditIcon />
        </a>
        {trip.delete && onDelete ? (
          <IconButton label={trip.delete.confirmation.action} tone="danger" onClick={onDelete}>
            <DeleteIcon />
          </IconButton>
        ) : null}
      </div>
    </div>
  );
}
