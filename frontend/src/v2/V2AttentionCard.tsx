import type { DashboardActionItem, V2TripItem } from "../types";
import { V2OfferSummary, V2TripCard } from "./V2TripCard";

const ATTENTION_COPY = {
  overbooked: "A skipped trip still has an active booking.",
  priceDrop: "The same itinerary is now available for less.",
  betterOption: "A better route clears your preference threshold.",
  needsBooking: "This departure is approaching without a booking.",
};

function daysBetween(today: string, anchorDate: string): number {
  const start = new Date(`${today}T12:00:00`).getTime();
  const end = new Date(`${anchorDate}T12:00:00`).getTime();
  return Math.round((end - start) / 86_400_000);
}

export function V2AttentionCard({ item, today }: { item: DashboardActionItem; today: string }) {
  if (item.kind === "unmatchedBooking") {
    return (
      <article className="v2-attention-card v2-attention-card--link">
        <header>
          <span className="v2-attention-card__signal">Needs review</span>
          <span className="v2-attention-card__date">{item.dateTile.weekday} · {item.dateTile.monthDay}</span>
        </header>
        <h3>Place this booking</h3>
        <p>Milemark imported the reservation but could not confidently assign it to a trip.</p>
        <V2OfferSummary offer={item.offer} kind="booked" />
        <div className="v2-attention-card__actions">
          <a className="v2-button v2-button--primary" href="/#action-items">Resolve in classic</a>
          <a className="v2-button v2-button--quiet" href={item.createTripHref}>Create trip</a>
        </div>
      </article>
    );
  }

  const tripItem: V2TripItem = {
    state: item.row.trip.skipped ? "skipped" : item.row.bookedOffer ? "booked" : "planning",
    daysUntil: daysBetween(today, item.row.trip.anchorDate),
    row: item.row,
  };
  return (
    <article className={`v2-attention-card v2-attention-card--${item.attentionKind}`}>
      <header>
        <span className="v2-attention-card__signal">{item.title}</span>
        <span>Decision</span>
      </header>
      <p>{ATTENTION_COPY[item.attentionKind]}</p>
      <V2TripCard item={tripItem} compact />
    </article>
  );
}
