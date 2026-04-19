import { useEffect, useMemo, useState } from "react";
import { useQueryClient } from "@tanstack/react-query";

import type { DashboardActionItem, DashboardUnmatchedBookingActionItem, TripRow as TripRowValue } from "../types";
import { prefetchTripEditorFromHref } from "../lib/tripEditorPrefetch";
import { DateTile } from "./DateTile";
import { DeleteIcon, EditIcon, LinkIcon } from "./Icons";
import { IconButton } from "./IconButton";
import { OfferBlock } from "./OfferBlock";
import { PrefetchLink } from "./PrefetchLink";
import { SearchSelectField } from "./SearchSelectField";
import { TripRow } from "./TripRow";

interface Props {
  items: DashboardActionItem[];
  onOpenBookings: (tripInstanceId: string, mode: "list" | "create", bookingId?: string) => void;
  onOpenTrackers: (tripInstanceId: string) => void;
  onDeleteTrip: (row: TripRowValue) => void;
  supportsTrackerPreview?: boolean;
  supportsTrackerHover?: boolean;
  onLinkUnmatchedBooking: (unmatchedBookingId: string, tripInstanceId: string) => Promise<void>;
  onEditUnmatchedBooking: (unmatchedBookingId: string) => void;
  onDeleteUnmatchedBooking: (unmatchedBookingId: string) => Promise<void>;
  onPrefetchBookings?: (tripInstanceId: string) => void;
  onPrefetchCreateBooking?: (tripInstanceId: string) => void;
  onPrefetchTrackers?: (tripInstanceId: string) => void;
}

export function ActionItemsSection({
  items,
  onOpenBookings,
  onOpenTrackers,
  onDeleteTrip,
  supportsTrackerPreview = false,
  supportsTrackerHover = false,
  onLinkUnmatchedBooking,
  onEditUnmatchedBooking,
  onDeleteUnmatchedBooking,
  onPrefetchBookings,
  onPrefetchCreateBooking,
  onPrefetchTrackers,
}: Props) {
  if (items.length === 0) {
    return null;
  }

  return (
    <section className="surface" id="needs-attention">
      <div className="surface__header">
        <h2>Action Items</h2>
      </div>
      <div className="attention-stack-react">
        {items.map((item) => (
          item.kind === "unmatchedBooking" ? (
            <UnmatchedBookingCard
              key={item.unmatchedBookingId}
              item={item}
              onLink={onLinkUnmatchedBooking}
              onEdit={onEditUnmatchedBooking}
              onDelete={onDeleteUnmatchedBooking}
            />
          ) : (
            <article
              key={`${item.attentionKind}-${item.row.trip.tripInstanceId}`}
              className={`attention-card attention-card--${item.attentionKind}`}
            >
              <div className="attention-card__header">
                <div>
                  <p className="attention-card__eyebrow">{item.title}</p>
                </div>
                {item.badge ? <span className="attention-card__badge">{item.badge}</span> : null}
              </div>
              <TripRow
                row={item.row}
                onOpenBookings={onOpenBookings}
                onOpenTrackers={onOpenTrackers}
                onDelete={onDeleteTrip}
                supportsTrackerPreview={supportsTrackerPreview}
                supportsTrackerHover={supportsTrackerHover}
                onPrefetchBookings={onPrefetchBookings}
                onPrefetchCreateBooking={onPrefetchCreateBooking}
                onPrefetchTrackers={onPrefetchTrackers}
              />
            </article>
          )
        ))}
      </div>
    </section>
  );
}

function UnmatchedBookingCard({
  item,
  onLink,
  onEdit,
  onDelete,
}: {
  item: DashboardUnmatchedBookingActionItem;
  onLink: (unmatchedBookingId: string, tripInstanceId: string) => Promise<void>;
  onEdit: (unmatchedBookingId: string) => void;
  onDelete: (unmatchedBookingId: string) => Promise<void>;
}) {
  const queryClient = useQueryClient();
  const firstOptionValue = useMemo(
    () => item.preferredTripInstanceId,
    [item.preferredTripInstanceId],
  );
  const tripOptions = useMemo(
    () => item.tripOptions.flatMap((group) => (
      group.options.map((option) => ({
        value: option.value,
        label: option.label,
        keywords: `${group.label} ${option.label}`,
        summary: option.label,
        groupLabel: group.label,
      }))
    )),
    [item.tripOptions],
  );
  const [selectedTripInstanceId, setSelectedTripInstanceId] = useState(firstOptionValue);
  const [pendingAction, setPendingAction] = useState<"" | "link">("");

  useEffect(() => {
    setSelectedTripInstanceId(firstOptionValue || "");
    setPendingAction("");
  }, [firstOptionValue, item.unmatchedBookingId]);

  async function handleLink() {
    if (!selectedTripInstanceId) {
      return;
    }
    setPendingAction("link");
    try {
      await onLink(item.unmatchedBookingId, selectedTripInstanceId);
    } finally {
      setPendingAction("");
    }
  }

  async function handleDelete() {
    await onDelete(item.unmatchedBookingId);
  }

  return (
    <article className="attention-card attention-card--unmatched">
      <div className="attention-card__header">
        <div>
          <p className="attention-card__eyebrow">{item.title}</p>
        </div>
      </div>
      <div className="attention-card__workflow">
        <div className="attention-card__booking-row">
          <DateTile tile={item.dateTile} />
          <div className="attention-card__offer-shell">
            <OfferBlock
              kind="booked"
              offer={item.offer}
              actions={(
                <div className="offer-action-cluster">
                  <IconButton label="Edit booking" variant="inline" onClick={() => onEdit(item.unmatchedBookingId)}>
                    <EditIcon />
                  </IconButton>
                  <IconButton
                    label="Delete booking"
                    tone="danger"
                    variant="inline"
                    onClick={() => void handleDelete()}
                    disabled={pendingAction !== ""}
                  >
                    <DeleteIcon />
                  </IconButton>
                </div>
              )}
            />
          </div>
        </div>
        <div className="attention-card__field attention-card__field--inline attention-card__field--compact">
          <SearchSelectField
            options={tripOptions.map((option) => ({ ...option, meta: option.groupLabel }))}
            value={selectedTripInstanceId}
            onChange={setSelectedTripInstanceId}
            placeholder="Choose one"
            ariaLabel="Link booking to trip"
            allowEmpty
            emptySelectionLabel="Choose one"
            renderOptionMeta={(option) => <small>{option.meta}</small>}
            disabled={pendingAction !== ""}
          />
        </div>
        <div className="attention-card__control-actions attention-card__control-actions--inline">
          <IconButton
            label="Link booking"
            disabled={!selectedTripInstanceId || pendingAction !== ""}
            variant="inline"
            onClick={() => void handleLink()}
            loading={pendingAction === "link"}
          >
            <LinkIcon />
          </IconButton>
          <div className="attention-card__alternate-action">
            {pendingAction ? (
              <span className="primary-button is-disabled" aria-disabled="true">
                Create trip
              </span>
            ) : (
              <PrefetchLink
                className="primary-button"
                to={item.createTripHref}
                onPrefetch={() => void prefetchTripEditorFromHref(queryClient, item.createTripHref)}
              >
                Create trip
              </PrefetchLink>
            )}
          </div>
        </div>
      </div>
    </article>
  );
}
