import type { TripRow as TripRowValue } from "../types";
import { OfferBlock } from "./OfferBlock";
import { TripIdentityRow } from "./TripIdentityRow";

interface Props {
  row: TripRowValue;
  onOpenBookings: (tripInstanceId: string, mode: "list" | "create", bookingId?: string) => void;
  onOpenTrackers: (tripInstanceId: string) => void;
  onDelete: (row: TripRowValue) => void;
}

export function TripRow({ row, onOpenBookings, onOpenTrackers, onDelete }: Props) {
  const tripInstanceId = row.trip.tripInstanceId;

  return (
    <article className="trip-row" id={`scheduled-${tripInstanceId}`}>
      <TripIdentityRow trip={row.trip} onDelete={() => onDelete(row)} />
      {row.bookedOffer ? (
        <OfferBlock
          kind="booked"
          offer={row.bookedOffer}
          onOpen={row.actions.showBookingModal ? () => onOpenBookings(tripInstanceId, "list") : undefined}
        />
      ) : (
        <OfferBlock
          kind="booked"
          offer={{
            label: "",
            detail: "",
            metaLabel: "",
            dayDeltaLabel: "",
            priceLabel: "",
            href: "",
            tone: "neutral",
            priceIsStatus: false,
            statusKind: "",
          }}
          emptyState
          onCreate={row.actions.canCreateBooking ? () => onOpenBookings(tripInstanceId, "create") : undefined}
        />
      )}
      {row.currentOffer ? (
        <OfferBlock
          kind="live"
          offer={row.currentOffer}
          onOpen={row.actions.showTrackers ? () => onOpenTrackers(tripInstanceId) : undefined}
        />
      ) : null}
    </article>
  );
}
