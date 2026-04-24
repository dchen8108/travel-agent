import { useQuery, useQueryClient } from "@tanstack/react-query";

import { api } from "../lib/api";
import { prefetchOnce } from "../lib/prefetch";
import { bookingFormQueryKey, bookingPanelQueryKey } from "../lib/queryKeys";
import type { BookingPanelPayload } from "../types";
import { EditIcon } from "./Icons";
import { IconButton } from "./IconButton";
import { OfferBlock } from "./OfferBlock";
import { TripIdentityRow } from "./TripIdentityRow";

interface Props {
  tripInstanceId: string;
  initialPanel: BookingPanelPayload | null;
  onChangeMode: (mode: "list" | "create" | "edit", bookingId?: string) => void;
}

function errorMessage(error: unknown, fallback: string) {
  return error instanceof Error ? error.message : fallback;
}

export function BookingInspector({
  tripInstanceId,
  initialPanel,
  onChangeMode,
}: Props) {
  const queryClient = useQueryClient();
  const listQuery = useQuery({
    queryKey: bookingPanelQueryKey(tripInstanceId),
    queryFn: () => api.bookingPanel(tripInstanceId),
    placeholderData: initialPanel ?? undefined,
  });

  function prefetchEditForm(bookingId: string) {
    void prefetchOnce(queryClient, {
      queryKey: bookingFormQueryKey(tripInstanceId, bookingId),
      queryFn: () => api.bookingForm(tripInstanceId, bookingId),
    });
  }

  const payload = listQuery.data;

  if (listQuery.isError) {
    return <div className="modal-loading">{errorMessage(listQuery.error, "Unable to load bookings.")}</div>;
  }

  if (!payload) {
    return <div className="modal-loading">Loading bookings…</div>;
  }

  return (
    <div className="modal-panel-stack">
      <div className="modal-panel-head">
        <TripIdentityRow trip={payload.trip} showEditAction={false} />
      </div>
      <div className="modal-list">
        {payload.rows.map((row) => (
          <article key={row.bookingId} className="modal-list-row modal-list-row--offer">
            <OfferBlock
              kind="booked"
              offer={row.offer}
              actions={listQuery.isPlaceholderData ? undefined : (
                <div className="offer-action-cluster">
                  <IconButton
                    label="Edit booking"
                    variant="inline"
                    onClick={() => onChangeMode("edit", row.bookingId)}
                    onMouseEnter={() => prefetchEditForm(row.bookingId)}
                    onFocus={() => prefetchEditForm(row.bookingId)}
                    onPointerDown={() => prefetchEditForm(row.bookingId)}
                  >
                    <EditIcon />
                  </IconButton>
                </div>
              )}
            />
            {listQuery.isPlaceholderData || !row.warning ? null : (
              <p className="modal-row-warning">{row.warning}</p>
            )}
          </article>
        ))}
      </div>
    </div>
  );
}
