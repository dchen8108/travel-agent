import { useQueryClient } from "@tanstack/react-query";

import { prefetchTripEditorFromHref } from "../lib/tripEditorPrefetch";
import type { TripRow as TripRowValue } from "../types";
import { AddIcon, DeleteIcon, EditIcon } from "./Icons";
import { IconButton } from "./IconButton";
import { OfferBlock } from "./OfferBlock";
import { OverflowMenu } from "./OverflowMenu";
import { TripIdentityRow } from "./TripIdentityRow";

interface Props {
  row: TripRowValue;
  onOpenBookings: (tripInstanceId: string, mode: "list" | "create" | "edit", bookingId?: string) => void;
  onOpenTrackers: (tripInstanceId: string) => void;
  onDelete: (row: TripRowValue) => void;
  isActive?: boolean;
  onPrefetchBookings?: (tripInstanceId: string) => void;
  onPrefetchCreateBooking?: (tripInstanceId: string) => void;
  onPrefetchEditBooking?: (tripInstanceId: string, bookingId: string) => void;
  onPrefetchTrackers?: (tripInstanceId: string) => void;
}

export function TripRow({
  row,
  onOpenBookings,
  onOpenTrackers,
  onDelete,
  isActive = false,
  onPrefetchBookings,
  onPrefetchCreateBooking,
  onPrefetchEditBooking,
  onPrefetchTrackers,
}: Props) {
  const queryClient = useQueryClient();
  const tripInstanceId = row.trip.tripInstanceId;
  const tripMenuItems = [
    ...(row.bookedOffer ? [{
      key: "add-booking",
      label: "+ Add Booking",
      icon: <AddIcon />,
      onSelect: () => onOpenBookings(tripInstanceId, "create"),
      onPrefetch: () => onPrefetchCreateBooking?.(tripInstanceId),
    }] : []),
    {
      key: "edit",
      label: "Edit",
      icon: <EditIcon />,
      href: row.trip.editHref,
      onPrefetch: () => void prefetchTripEditorFromHref(queryClient, row.trip.editHref),
    },
    ...(row.trip.delete ? [{
      key: "delete",
      label: "Delete",
      tone: "danger" as const,
      icon: <DeleteIcon />,
      onSelect: () => onDelete(row),
    }] : []),
  ];

  return (
    <article className={`trip-row${isActive ? " trip-row--active" : ""}`} id={`scheduled-${tripInstanceId}`}>
      <TripIdentityRow
        trip={row.trip}
        showEditAction={false}
        actions={(
          <OverflowMenu
            label="Trip actions"
            items={tripMenuItems}
          />
        )}
      />
      {row.bookedOffer ? (
        <OfferBlock
          kind="booked"
          offer={row.bookedOffer}
          onOpen={row.actions.showBookingModal ? () => onOpenBookings(tripInstanceId, "list") : undefined}
          onPrefetchAction={row.actions.showBookingModal ? () => onPrefetchBookings?.(tripInstanceId) : undefined}
          actions={
            row.actions.editBookingId ? (
              <div className="offer-action-cluster">
                <IconButton
                  label="Edit booking"
                  variant="inline"
                  onClick={() => onOpenBookings(tripInstanceId, "edit", row.actions.editBookingId)}
                  onMouseEnter={() => onPrefetchEditBooking?.(tripInstanceId, row.actions.editBookingId)}
                  onFocus={() => onPrefetchEditBooking?.(tripInstanceId, row.actions.editBookingId)}
                  onPointerDown={() => onPrefetchEditBooking?.(tripInstanceId, row.actions.editBookingId)}
                >
                  <EditIcon />
                </IconButton>
              </div>
            ) : undefined
          }
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
