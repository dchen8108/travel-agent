import { useQueryClient } from "@tanstack/react-query";
import type { ReactNode } from "react";

import type { TripIdentity } from "../types";
import { prefetchTripEditorFromHref } from "../lib/tripEditorPrefetch";
import { DateTile } from "./DateTile";
import { DeleteIcon, EditIcon } from "./Icons";
import { OverflowMenu } from "./OverflowMenu";

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
    <OverflowMenu
      label="Trip actions"
      items={[
        ...(showEditAction ? [{
          key: "edit",
          label: "Edit",
          icon: <EditIcon />,
          href: trip.editHref,
          onPrefetch: () => void prefetchTripEditorFromHref(queryClient, trip.editHref),
        }] : []),
        ...(trip.delete && onDelete ? [{
          key: "delete",
          label: "Delete",
          tone: "danger" as const,
          icon: <DeleteIcon />,
          onSelect: onDelete,
        }] : []),
      ]}
    />
  ) : null);

  return (
    <div className="trip-identity-row">
      <DateTile tile={trip.dateTile} />
      <div className="trip-identity-row__copy">
        <div className="trip-identity-row__titleline">
          <h3>{trip.title}</h3>
          {renderedActions ? <div className="trip-identity-row__actions">{renderedActions}</div> : null}
        </div>
      </div>
    </div>
  );
}
