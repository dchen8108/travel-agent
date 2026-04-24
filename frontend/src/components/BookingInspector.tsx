import { useQuery, useQueryClient } from "@tanstack/react-query";

import { api } from "../lib/api";
import { prefetchOnce } from "../lib/prefetch";
import { bookingFormQueryKey, bookingPanelQueryKey } from "../lib/queryKeys";
import type { BookingPanelPayload } from "../types";
import { useConfirm } from "./ConfirmProvider";
import { AddIcon, DeleteIcon, DetachIcon, EditIcon } from "./Icons";
import { OfferBlock } from "./OfferBlock";
import { OverflowMenu } from "./OverflowMenu";
import { TripIdentityRow } from "./TripIdentityRow";
import { useToast } from "./ToastProvider";

interface Props {
  tripInstanceId: string;
  initialPanel: BookingPanelPayload | null;
  dashboardFilters: URLSearchParams;
  onChangeMode: (mode: "list" | "create" | "edit", bookingId?: string) => void;
  onPanelResult: (tripInstanceId: string, panel: BookingPanelPayload | null) => Promise<void>;
}

function errorMessage(error: unknown, fallback: string) {
  return error instanceof Error ? error.message : fallback;
}

export function BookingInspector({
  tripInstanceId,
  initialPanel,
  dashboardFilters,
  onChangeMode,
  onPanelResult,
}: Props) {
  const queryClient = useQueryClient();
  const { confirm } = useConfirm();
  const { pushToast } = useToast();
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

  async function handleDelete(bookingId: string) {
    const approved = await confirm({
      title: "Delete this booking?",
      description: "This removes it from the trip and from the app.",
      actionLabel: "Delete booking",
      cancelLabel: "Keep booking",
      tone: "danger",
    });
    if (!approved) {
      return;
    }
    try {
      const result = await api.deleteBooking(bookingId, dashboardFilters);
      await onPanelResult(tripInstanceId, result.panel);
      pushToast({ message: "Booking deleted" });
    } catch (error) {
      pushToast({ message: errorMessage(error, "Unable to delete booking."), kind: "error" });
    }
  }

  async function handleDetach(bookingId: string) {
    const approved = await confirm({
      title: "Detach this booking from the trip?",
      description: "It will move back to needs linking.",
      actionLabel: "Detach booking",
      cancelLabel: "Keep booking",
    });
    if (!approved) {
      return;
    }
    try {
      const result = await api.unlinkBooking(bookingId, dashboardFilters);
      await onPanelResult(tripInstanceId, result.panel);
      pushToast({ message: "Booking needs linking" });
    } catch (error) {
      pushToast({ message: errorMessage(error, "Unable to detach booking."), kind: "error" });
    }
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
                <OverflowMenu
                  label="Booking actions"
                  items={[
                    {
                      key: "add-booking",
                      label: "New",
                      icon: <AddIcon />,
                      onSelect: () => onChangeMode("create"),
                    },
                    {
                      key: "edit-booking",
                      label: "Edit",
                      icon: <EditIcon />,
                      onSelect: () => onChangeMode("edit", row.bookingId),
                      onPrefetch: () => prefetchEditForm(row.bookingId),
                    },
                    {
                      key: "detach-booking",
                      label: "Detach",
                      icon: <DetachIcon />,
                      onSelect: () => void handleDetach(row.bookingId),
                    },
                    {
                      key: "delete-booking",
                      label: "Delete",
                      tone: "danger",
                      icon: <DeleteIcon />,
                      onSelect: () => void handleDelete(row.bookingId),
                    },
                  ]}
                />
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
