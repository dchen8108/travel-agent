import type { TripRow as TripRowValue } from "../types";
import { OfferBlock } from "./OfferBlock";
import { TripIdentityRow } from "./TripIdentityRow";

interface Props {
  row: TripRowValue;
  onOpenBookings: (tripInstanceId: string, mode: "list" | "create", bookingId?: string) => void;
  onOpenTrackers: (tripInstanceId: string) => void;
  onDelete: (row: TripRowValue) => void;
  onPrefetchBookings?: (tripInstanceId: string) => void;
  onPrefetchCreateBooking?: (tripInstanceId: string) => void;
  onPrefetchTrackers?: (tripInstanceId: string) => void;
}

export function TripRow({
  row,
  onOpenBookings,
  onOpenTrackers,
  onDelete,
  onPrefetchBookings,
  onPrefetchCreateBooking,
  onPrefetchTrackers,
}: Props) {
  const tripInstanceId = row.trip.tripInstanceId;

  return (
    <article className="trip-row" id={`scheduled-${tripInstanceId}`}>
      <TripIdentityRow trip={row.trip} onDelete={() => onDelete(row)} />
      {row.bookedOffer ? (
        <OfferBlock
          kind="booked"
          offer={row.bookedOffer}
          onOpen={row.actions.showBookingModal ? () => onOpenBookings(tripInstanceId, "list") : undefined}
          onPrefetchAction={row.actions.showBookingModal ? () => onPrefetchBookings?.(tripInstanceId) : undefined}
        />
      ) : (
        <OfferBlock
          kind="booked"
          offer={{
            label: "",
            detail: "",
            airlineKey: "",
            primaryMetaLabel: "",
            metaBadges: [],
            metaLabel: "",
            priceLabel: "",
            href: "",
            tone: "neutral",
            priceIsStatus: false,
            statusKind: "",
          }}
          emptyState
          onCreate={row.actions.canCreateBooking ? () => onOpenBookings(tripInstanceId, "create") : undefined}
          onPrefetchAction={row.actions.canCreateBooking ? () => onPrefetchCreateBooking?.(tripInstanceId) : undefined}
        />
      )}
      {row.currentOffer ? (
        <OfferBlock
          kind="live"
          offer={row.currentOffer}
          onOpen={row.actions.showTrackers ? () => onOpenTrackers(tripInstanceId) : undefined}
          onPrefetchAction={row.actions.showTrackers ? () => onPrefetchTrackers?.(tripInstanceId) : undefined}
        />
      ) : null}
    </article>
  );
}
