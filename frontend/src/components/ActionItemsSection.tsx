import { useMemo, useState } from "react";

import type { DashboardActionItem, DashboardUnmatchedBookingActionItem, TripRow as TripRowValue } from "../types";
import { DeleteIcon } from "./Icons";
import { IconButton } from "./IconButton";
import { OfferBlock } from "./OfferBlock";
import { TripRow } from "./TripRow";

interface Props {
  items: DashboardActionItem[];
  onOpenBookings: (tripInstanceId: string, mode: "list" | "create", bookingId?: string) => void;
  onOpenTrackers: (tripInstanceId: string) => void;
  onDeleteTrip: (row: TripRowValue) => void;
  onLinkUnmatchedBooking: (unmatchedBookingId: string, tripInstanceId: string) => Promise<void>;
  onDeleteUnmatchedBooking: (unmatchedBookingId: string) => Promise<void>;
}

export function ActionItemsSection({
  items,
  onOpenBookings,
  onOpenTrackers,
  onDeleteTrip,
  onLinkUnmatchedBooking,
  onDeleteUnmatchedBooking,
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
  onDelete,
}: {
  item: DashboardUnmatchedBookingActionItem;
  onLink: (unmatchedBookingId: string, tripInstanceId: string) => Promise<void>;
  onDelete: (unmatchedBookingId: string) => Promise<void>;
}) {
  const firstOptionValue = useMemo(
    () => item.tripOptions.flatMap((group) => group.options)[0]?.value ?? "",
    [item.tripOptions],
  );
  const [selectedTripInstanceId, setSelectedTripInstanceId] = useState(firstOptionValue);

  return (
    <article className="attention-card attention-card--unmatched">
      <div className="attention-card__header">
        <div>
          <p className="attention-card__eyebrow">{item.title}</p>
          <h3 className="attention-card__title">{item.suggestedTripLabel}</h3>
          <p className="attention-card__meta">{item.sourceLabel}</p>
        </div>
        <IconButton label="Delete booking" tone="danger" onClick={() => onDelete(item.unmatchedBookingId)}>
          <DeleteIcon />
        </IconButton>
      </div>
      <div className="attention-card__offer-shell">
        <OfferBlock kind="booked" offer={item.offer} />
      </div>
      <div className="attention-card__controls">
        <label className="attention-card__field">
          <span>Scheduled trip</span>
          <select
            value={selectedTripInstanceId}
            onChange={(event) => setSelectedTripInstanceId(event.target.value)}
          >
            <option value="">Choose one</option>
            {item.tripOptions.map((group) => (
              <optgroup key={group.label} label={group.label}>
                {group.options.map((option) => (
                  <option key={option.value} value={option.value}>{option.label}</option>
                ))}
              </optgroup>
            ))}
          </select>
        </label>
        <div className="attention-card__control-actions">
          <button
            type="button"
            className="primary-button"
            disabled={!selectedTripInstanceId}
            onClick={() => onLink(item.unmatchedBookingId, selectedTripInstanceId)}
          >
            Link booking
          </button>
          <a className="secondary-button" href={item.createTripHref}>Create trip</a>
        </div>
      </div>
    </article>
  );
}
