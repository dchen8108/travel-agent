import type { Offer, TripRow, V2TripItem } from "../types";
import { AirlineMark } from "../components/AirlineMark";
import { AlertIcon } from "../components/Icons";

interface TripCardProps {
  item: V2TripItem;
  compact?: boolean;
}

function bookingAction(row: TripRow): { href: string; label: string } | null {
  const tripInstanceId = encodeURIComponent(row.trip.tripInstanceId);
  if (row.actions.showBookingModal) {
    return {
      href: `/?panel=bookings&trip_instance_id=${tripInstanceId}`,
      label: "Bookings",
    };
  }
  if (row.actions.editBookingId) {
    return {
      href: `/?panel=bookings&trip_instance_id=${tripInstanceId}&booking_mode=edit&booking_id=${encodeURIComponent(row.actions.editBookingId)}`,
      label: "Edit booking",
    };
  }
  if (row.actions.canCreateBooking) {
    return {
      href: `/?panel=bookings&trip_instance_id=${tripInstanceId}&booking_mode=create`,
      label: "Add booking",
    };
  }
  return null;
}

function timingLabel(daysUntil: number): string {
  if (daysUntil === 0) return "Today";
  if (daysUntil === 1) return "Tomorrow";
  if (daysUntil > 1 && daysUntil < 7) return `In ${daysUntil} days`;
  return "Upcoming";
}

export function V2OfferSummary({ offer, kind }: { offer: Offer; kind: "booked" | "live" }) {
  const body = (
    <>
      <span className="v2-offer__mark"><AirlineMark airlineKey={offer.airlineKey} /></span>
      <span className="v2-offer__copy">
        <span className="v2-offer__label">{offer.label || (kind === "booked" ? "Booked" : "Live fare")}</span>
        <span className="v2-offer__route">
          {offer.detail}
          {offer.warning ? (
            <span className="v2-offer__warning" title={offer.warning} aria-label={offer.warning}>
              <AlertIcon />
            </span>
          ) : null}
        </span>
        {offer.primaryMetaLabel ? <span className="v2-offer__meta">{offer.primaryMetaLabel}</span> : null}
      </span>
      <strong className={`v2-offer__price v2-offer__price--${kind}`}>{offer.priceLabel}</strong>
    </>
  );

  return offer.href ? (
    <a className="v2-offer v2-offer--link" href={offer.href} target="_blank" rel="noreferrer">
      {body}
    </a>
  ) : (
    <div className="v2-offer">{body}</div>
  );
}

export function V2TripCard({ item, compact = false }: TripCardProps) {
  const { row, state, daysUntil } = item;
  const booking = bookingAction(row);
  const trackerHref = row.actions.showTrackers
    ? `/?panel=trackers&trip_instance_id=${encodeURIComponent(row.trip.tripInstanceId)}`
    : "";

  return (
    <article className={`v2-trip-card v2-trip-card--${state}${compact ? " v2-trip-card--compact" : ""}`}>
      <div className="v2-trip-card__date" aria-label={`${row.trip.dateTile.weekday} ${row.trip.dateTile.monthDay}`}>
        <span>{row.trip.dateTile.weekday}</span>
        <strong>{row.trip.dateTile.monthDay}</strong>
      </div>
      <div className="v2-trip-card__identity">
        <span className={`v2-state v2-state--${state}`}>{state === "planning" ? "Plan" : state}</span>
        <h3>{row.trip.title}</h3>
        <span className="v2-trip-card__timing">{timingLabel(daysUntil)}</span>
        <div className="v2-trip-card__actions">
          <a href={row.trip.editHref}>Edit trip</a>
          {booking ? <a href={booking.href}>{booking.label}</a> : null}
          {trackerHref ? <a href={trackerHref}>Flights</a> : null}
        </div>
      </div>
      <div className="v2-trip-card__offers">
        {row.bookedOffer ? <V2OfferSummary offer={row.bookedOffer} kind="booked" /> : (
          <div className="v2-offer v2-offer--empty">
            <span className="v2-offer__empty-kicker">Booking</span>
            <span>Not booked yet</span>
          </div>
        )}
        {row.currentOffer ? <V2OfferSummary offer={row.currentOffer} kind="live" /> : (
          <div className="v2-offer v2-offer--empty">
            <span className="v2-offer__empty-kicker">Live fare</span>
            <span>Initializing</span>
          </div>
        )}
      </div>
    </article>
  );
}
