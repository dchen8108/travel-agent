import { useEffect, useRef, useState } from "react";

import { useQueryClient } from "@tanstack/react-query";

import type { CollectionCard as CollectionCardValue } from "../types";
import { prefetchTripEditorFromHref } from "../lib/tripEditorPrefetch";
import { AddIcon, DeleteIcon, EditIcon } from "./Icons";
import { CollectionNameEditor } from "./CollectionNameEditor";
import { OverflowMenu } from "./OverflowMenu";
import { PrefetchLink } from "./PrefetchLink";

interface Props {
  collection: CollectionCardValue;
  onEdit: () => void;
  onDelete?: () => void;
  onCancelEdit?: () => void;
  onSaveEdit?: (label: string) => Promise<unknown>;
  onToggleRecurringTrip: (tripId: string, active: boolean) => void;
  pendingRecurringTripId?: string;
  editing?: boolean;
}

export function CollectionCard({
  collection,
  onEdit,
  onDelete,
  onCancelEdit,
  onSaveEdit,
  onToggleRecurringTrip,
  pendingRecurringTripId = "",
  editing = false,
}: Props) {
  const queryClient = useQueryClient();
  const pillRailRef = useRef<HTMLDivElement | null>(null);
  const [pillsExpanded, setPillsExpanded] = useState(false);
  const [pillRailCanExpand, setPillRailCanExpand] = useState(false);
  const [pillRailCollapsedHeight, setPillRailCollapsedHeight] = useState(0);

  useEffect(() => {
    setPillsExpanded(false);
  }, [collection.groupId, collection.upcomingTrips.length]);

  useEffect(() => {
    const rail = pillRailRef.current;
    if (!rail) {
      setPillRailCanExpand(false);
      return;
    }

    const recompute = () => {
      const firstPill = rail.querySelector<HTMLElement>(".trip-pill");
      if (!firstPill) {
        setPillRailCanExpand(false);
        setPillRailCollapsedHeight(0);
        return;
      }
      const styles = window.getComputedStyle(rail);
      const rowGap = Number.parseFloat(styles.rowGap || styles.gap || "0") || 0;
      const collapsedHeight = firstPill.getBoundingClientRect().height * 2 + rowGap;
      setPillRailCollapsedHeight(collapsedHeight);
      setPillRailCanExpand(rail.scrollHeight > collapsedHeight + 1);
    };

    recompute();

    if (typeof ResizeObserver !== "undefined") {
      const observer = new ResizeObserver(() => {
        recompute();
      });
      observer.observe(rail);
      return () => observer.disconnect();
    }

    window.addEventListener("resize", recompute);
    return () => window.removeEventListener("resize", recompute);
  }, [collection.upcomingTrips.length]);

  return (
    <article className="collection-card" id={`group-${collection.groupId}`}>
      <div className="collection-card__header">
        <div className="collection-card__titleblock">
          {editing ? (
            <CollectionNameEditor
              mode="edit"
              variant="inline"
              initialLabel={collection.label}
              onCancel={() => onCancelEdit?.()}
              onSave={(nextLabel) => onSaveEdit?.(nextLabel) ?? Promise.resolve()}
            />
          ) : (
            <div className="collection-card__titleline">
              <h3>{collection.label}</h3>
              <OverflowMenu
                label="Collection actions"
                items={[
                  {
                    key: "add",
                    label: "+ Create Trip",
                    icon: <AddIcon />,
                    href: collection.createTripHref,
                    onPrefetch: () => void prefetchTripEditorFromHref(queryClient, collection.createTripHref),
                  },
                  {
                    key: "edit",
                    label: "Edit",
                    icon: <EditIcon />,
                    onSelect: onEdit,
                  },
                  ...(onDelete ? [{
                    key: "delete",
                    label: "Delete",
                    tone: "danger" as const,
                    icon: <DeleteIcon />,
                    onSelect: onDelete,
                  }] : []),
                ]}
              />
            </div>
          )}
        </div>
      </div>
      {collection.recurringTrips.length > 0 ? (
        <div className="recurring-grid">
          {collection.recurringTrips.map((trip) => (
            <article className="recurring-card" key={trip.tripId}>
              <div className="recurring-card__copy">
                <div className="recurring-card__titleline">
                  <strong>{trip.label}</strong>
                  <PrefetchLink
                    className="icon-link icon-link--inline"
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
      <div className="collection-card__pill-section">
        <div
          ref={pillRailRef}
          className={`pill-row${pillRailCanExpand ? " pill-row--overflowing" : ""}${!pillsExpanded ? " pill-row--collapsed" : ""}`}
          style={!pillsExpanded && pillRailCanExpand && pillRailCollapsedHeight ? { maxHeight: `${pillRailCollapsedHeight}px` } : undefined}
        >
          {collection.upcomingTrips.length > 0 ? (
            collection.upcomingTrips.map((trip) => (
              <span
                key={trip.tripInstanceId}
                className={`trip-pill trip-pill--${trip.lifecycle}${trip.attentionKind ? ` trip-pill--attention-${trip.attentionKind}` : ""}`}
                title={trip.title}
              >
                <span>{trip.label}</span>
              </span>
            ))
          ) : (
            <p className="empty-copy">No trips yet.</p>
          )}
        </div>
        {pillRailCanExpand ? (
          <div className="collection-card__pill-toggle">
            <button type="button" className="ghost-button" onClick={() => setPillsExpanded((current) => !current)}>
              {pillsExpanded ? "Show less" : "Show all"}
            </button>
          </div>
        ) : null}
      </div>
    </article>
  );
}
