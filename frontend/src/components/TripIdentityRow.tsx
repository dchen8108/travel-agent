import { useQueryClient } from "@tanstack/react-query";
import type { ReactNode } from "react";

import type { TripIdentity } from "../types";
import { prefetchTripEditorFromHref } from "../lib/tripEditorPrefetch";
import { DateTile } from "./DateTile";
import { DeleteIcon, EditIcon } from "./Icons";
import { IconButton } from "./IconButton";
import { PrefetchLink } from "./PrefetchLink";

interface Props {
  trip: TripIdentity;
  onDelete?: () => void;
  showEditAction?: boolean;
  actions?: ReactNode;
}

export function TripIdentityRow({ trip, onDelete, showEditAction = true, actions }: Props) {
  const queryClient = useQueryClient();
  const hasDefaultActions = showEditAction || (trip.delete && onDelete);
  const renderedActions = actions ?? (hasDefaultActions ? (
    <>
      {showEditAction ? (
        <PrefetchLink
          className="icon-link icon-link--inline"
          to={trip.editHref}
          aria-label="Edit trip"
          title="Edit trip"
          onPrefetch={() => void prefetchTripEditorFromHref(queryClient, trip.editHref)}
        >
          <EditIcon />
        </PrefetchLink>
      ) : null}
      {trip.delete && onDelete ? (
        <IconButton label={trip.delete.confirmation.action} tone="danger" variant="inline" onClick={onDelete}>
          <DeleteIcon />
        </IconButton>
      ) : null}
    </>
  ) : null);

  return (
    <div className="trip-identity-row">
      <DateTile tile={trip.dateTile} />
      <div className="trip-identity-row__copy">
        <h3>{trip.title}</h3>
      </div>
      {renderedActions ? <div className="trip-identity-row__actions">{renderedActions}</div> : null}
    </div>
  );
}
