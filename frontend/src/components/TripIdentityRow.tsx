import { useQueryClient } from "@tanstack/react-query";
import { useEffect, useRef, useState, type ReactNode } from "react";

import type { TripIdentity } from "../types";
import { prefetchTripEditorFromHref } from "../lib/tripEditorPrefetch";
import { DateTile } from "./DateTile";
import { DeleteIcon, EditIcon, MoreIcon } from "./Icons";
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
    <TripActionsMenu
      trip={trip}
      showEditAction={showEditAction}
      onDelete={trip.delete && onDelete ? onDelete : undefined}
      onPrefetchEdit={() => void prefetchTripEditorFromHref(queryClient, trip.editHref)}
    />
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

function TripActionsMenu({
  trip,
  showEditAction,
  onDelete,
  onPrefetchEdit,
}: {
  trip: TripIdentity;
  showEditAction: boolean;
  onDelete?: () => void;
  onPrefetchEdit: () => void;
}) {
  const [open, setOpen] = useState(false);
  const menuRef = useRef<HTMLDivElement | null>(null);

  useEffect(() => {
    if (!open) {
      return;
    }

    function handlePointerDown(event: PointerEvent) {
      if (!menuRef.current?.contains(event.target as Node)) {
        setOpen(false);
      }
    }

    function handleKeyDown(event: KeyboardEvent) {
      if (event.key === "Escape") {
        setOpen(false);
      }
    }

    window.addEventListener("pointerdown", handlePointerDown);
    window.addEventListener("keydown", handleKeyDown);
    return () => {
      window.removeEventListener("pointerdown", handlePointerDown);
      window.removeEventListener("keydown", handleKeyDown);
    };
  }, [open]);

  return (
    <div className="trip-actions-menu" ref={menuRef}>
      <IconButton
        label="Trip actions"
        variant="inline"
        className={open ? "trip-actions-menu__trigger is-open" : "trip-actions-menu__trigger"}
        aria-haspopup="menu"
        aria-expanded={open}
        onClick={() => setOpen((current) => !current)}
      >
        <MoreIcon />
      </IconButton>
      {open ? (
        <div className="trip-actions-menu__dropdown" role="menu" aria-label="Trip actions">
          {showEditAction ? (
            <PrefetchLink
              className="trip-actions-menu__item"
              to={trip.editHref}
              role="menuitem"
              onPrefetch={onPrefetchEdit}
              onClick={() => setOpen(false)}
            >
              <EditIcon />
              <span>Edit</span>
            </PrefetchLink>
          ) : null}
          {onDelete ? (
            <button
              type="button"
              className="trip-actions-menu__item trip-actions-menu__item--danger"
              role="menuitem"
              onClick={() => {
                setOpen(false);
                onDelete();
              }}
            >
              <DeleteIcon />
              <span>Delete</span>
            </button>
          ) : null}
        </div>
      ) : null}
    </div>
  );
}
