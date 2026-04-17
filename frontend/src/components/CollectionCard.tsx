import { useEffect, useState, type KeyboardEvent } from "react";

import { useQueryClient } from "@tanstack/react-query";

import type { CollectionCard as CollectionCardValue } from "../types";
import { prefetchTripEditorFromHref } from "../lib/tripEditorPrefetch";
import { CheckIcon, CloseIcon, EditIcon } from "./Icons";
import { IconButton } from "./IconButton";
import { PrefetchLink } from "./PrefetchLink";

interface Props {
  collection: CollectionCardValue;
  onEdit: () => void;
  onCancelEdit?: () => void;
  onSaveEdit?: (label: string) => Promise<unknown>;
  onToggleRecurringTrip: (tripId: string, active: boolean) => void;
  pendingRecurringTripId?: string;
  editing?: boolean;
}

export function CollectionCard({
  collection,
  onEdit,
  onCancelEdit,
  onSaveEdit,
  onToggleRecurringTrip,
  pendingRecurringTripId = "",
  editing = false,
}: Props) {
  const queryClient = useQueryClient();
  const [label, setLabel] = useState(collection.label);
  const [error, setError] = useState("");
  const [saving, setSaving] = useState(false);

  useEffect(() => {
    setLabel(collection.label);
  }, [collection.label]);

  useEffect(() => {
    if (!editing) {
      setError("");
      setSaving(false);
      setLabel(collection.label);
    }
  }, [collection.label, editing]);

  async function handleSave() {
    if (!onSaveEdit) {
      return;
    }
    setSaving(true);
    setError("");
    try {
      await onSaveEdit(label);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Unable to save collection.");
      setSaving(false);
    }
  }

  function handleCancel() {
    setError("");
    setSaving(false);
    setLabel(collection.label);
    onCancelEdit?.();
  }

  function handleKeyDown(event: KeyboardEvent<HTMLInputElement>) {
    if (event.key === "Escape") {
      event.preventDefault();
      handleCancel();
      return;
    }
    if (event.key === "Enter") {
      event.preventDefault();
      void handleSave();
    }
  }

  return (
    <article className="collection-card" id={`group-${collection.groupId}`}>
      <div className="collection-card__header">
        <div className="collection-card__titleblock">
          <div className="collection-card__titleline">
            {editing ? (
              <>
                <input
                  className="collection-card__input collection-card__input--inline"
                  value={label}
                  onChange={(event) => setLabel(event.target.value)}
                  onKeyDown={handleKeyDown}
                  placeholder="Collection name"
                  disabled={saving}
                  autoFocus
                />
                <div className="collection-card__header-actions collection-card__header-actions--inline">
                  <IconButton label="Save collection" onClick={() => void handleSave()} disabled={saving}>
                    <CheckIcon />
                  </IconButton>
                  <IconButton label="Cancel" onClick={handleCancel} disabled={saving}>
                    <CloseIcon />
                  </IconButton>
                </div>
              </>
            ) : (
              <>
                <h3>{collection.label}</h3>
                <IconButton label="Edit collection" onClick={onEdit}>
                  <EditIcon />
                </IconButton>
              </>
            )}
          </div>
          {editing && error ? <p className="inline-error">{error}</p> : null}
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
