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
  onLinkUnmatchedBooking: (unmatchedBookingId: string, tripInstanceId: string) => Promise<void>;
  onEditUnmatchedBooking: (unmatchedBookingId: string) => void;
  onDeleteUnmatchedBooking: (unmatchedBookingId: string) => Promise<void>;
  onPrefetchBookings?: (tripInstanceId: string) => void;
  onPrefetchTrackers?: (tripInstanceId: string) => void;
}

export function ActionItemsSection({
  items,
  onOpenBookings,
  onOpenTrackers,
  onDeleteTrip,
  onLinkUnmatchedBooking,
  onEditUnmatchedBooking,
  onDeleteUnmatchedBooking,
  onPrefetchBookings,
  onPrefetchTrackers,
}: Props) {
  return (
    <section className="surface" id="needs-attention">
      <div className="surface__header">
        <h2>Action Items</h2>
      </div>
      {items.length === 0 ? (
        <article className="quiet-state-card">
          <strong>No travel decisions are waiting.</strong>
          <p>Upcoming trips are covered, bookings are attached, and there are no fare changes to review.</p>
        </article>
      ) : (
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
                  onPrefetchBookings={onPrefetchBookings}
                  onPrefetchTrackers={onPrefetchTrackers}
                />
              </article>
            )
          ))}
        </div>
      )}
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

  useEffect(() => {
    setSelectedTripInstanceId(firstOptionValue || "");
  }, [firstOptionValue, item.unmatchedBookingId]);

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
                  <IconButton label="Edit booking" onClick={() => onEdit(item.unmatchedBookingId)}>
                    <EditIcon />
                  </IconButton>
                  <IconButton label="Delete booking" tone="danger" onClick={() => onDelete(item.unmatchedBookingId)}>
                    <DeleteIcon />
                  </IconButton>
                </div>
              )}
            />
          </div>
        </div>
        <label className="attention-card__field attention-card__field--inline">
          <span>Link to trip</span>
          <SearchSelectField
            options={tripOptions.map((option) => ({ ...option, meta: option.groupLabel }))}
            value={selectedTripInstanceId}
            onChange={setSelectedTripInstanceId}
            placeholder="Choose scheduled trip"
            allowEmpty
            emptySelectionLabel="Choose one"
            renderOptionMeta={(option) => <small>{option.meta}</small>}
          />
        </label>
        <div className="attention-card__control-actions attention-card__control-actions--inline">
          <IconButton
            label="Link booking"
            disabled={!selectedTripInstanceId}
            tone="accent"
            onClick={() => onLink(item.unmatchedBookingId, selectedTripInstanceId)}
          >
            <LinkIcon />
          </IconButton>
          <div className="attention-card__alternate-action">
            <PrefetchLink
              className="secondary-button"
              to={item.createTripHref}
              onPrefetch={() => void prefetchTripEditorFromHref(queryClient, item.createTripHref)}
            >
              Create trip
            </PrefetchLink>
          </div>
        </div>
      </div>
    </article>
  );
}
