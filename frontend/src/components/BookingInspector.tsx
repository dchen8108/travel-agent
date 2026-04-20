import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";

import { api } from "../lib/api";
import { prefetchOnce } from "../lib/prefetch";
import { bookingFormQueryKey, bookingFormQueryPrefix, bookingPanelQueryKey } from "../lib/queryKeys";
import type { BookingPanelPayload } from "../types";
import { useConfirm } from "./ConfirmProvider";
import { DeleteIcon, DetachIcon, EditIcon } from "./Icons";
import { IconButton } from "./IconButton";
import { OfferBlock } from "./OfferBlock";
import { useToast } from "./ToastProvider";
import { TripIdentityRow } from "./TripIdentityRow";

interface Props {
  tripInstanceId: string;
  initialPanel: BookingPanelPayload | null;
  dashboardFilters: URLSearchParams;
  onRefreshDashboard: () => void;
  onChangeMode: (mode: "list" | "create" | "edit", bookingId?: string) => void;
}

function errorMessage(error: unknown, fallback: string) {
  return error instanceof Error ? error.message : fallback;
}

export function BookingInspector({
  tripInstanceId,
  initialPanel,
  dashboardFilters,
  onRefreshDashboard,
  onChangeMode,
}: Props) {
  const queryClient = useQueryClient();
  const { pushToast } = useToast();
  const { confirm } = useConfirm();
  const listQuery = useQuery({
    queryKey: bookingPanelQueryKey(tripInstanceId),
    queryFn: () => api.bookingPanel(tripInstanceId),
    placeholderData: initialPanel ?? undefined,
  });

  const rowMutation = useMutation({
    mutationFn: async ({ bookingId, kind }: { bookingId: string; kind: "delete" | "unlink" }) => {
      if (kind === "delete") {
        return api.deleteBooking(bookingId, dashboardFilters);
      }
      return api.unlinkBooking(bookingId, dashboardFilters);
    },
    onSuccess: (result, variables) => {
      if (result.panel) {
        queryClient.setQueryData(bookingPanelQueryKey(tripInstanceId), result.panel);
      }
      onRefreshDashboard();
      queryClient.removeQueries({ queryKey: bookingFormQueryPrefix(tripInstanceId) });
      onChangeMode("list");
      pushToast({ message: variables.kind === "delete" ? "Booking deleted" : "Booking needs linking" });
    },
  });

  function prefetchCreateForm() {
    void prefetchOnce(queryClient, {
      queryKey: bookingFormQueryKey(tripInstanceId),
      queryFn: () => api.bookingForm(tripInstanceId),
    });
  }

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
      await rowMutation.mutateAsync({ bookingId, kind: "delete" });
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
      await rowMutation.mutateAsync({ bookingId, kind: "unlink" });
    } catch (error) {
      pushToast({ message: errorMessage(error, "Unable to detach booking."), kind: "error" });
    }
  }

  const payload = listQuery.data;
  const pendingRowBookingId = rowMutation.isPending ? rowMutation.variables?.bookingId ?? "" : "";
  const pendingRowKind = rowMutation.isPending ? rowMutation.variables?.kind ?? "" : "";

  if (listQuery.isError) {
    return <div className="modal-loading">{errorMessage(listQuery.error, "Unable to load bookings.")}</div>;
  }

  if (!payload) {
    return <div className="modal-loading">Loading bookings…</div>;
  }

  return (
    <div className="modal-panel-stack">
      <div className="modal-panel-head">
        <TripIdentityRow trip={payload.trip} />
        <button
          type="button"
          className="primary-button"
          onClick={() => onChangeMode("create")}
          onMouseEnter={prefetchCreateForm}
          onFocus={prefetchCreateForm}
          onPointerDown={prefetchCreateForm}
          disabled={rowMutation.isPending}
        >
          Create booking
        </button>
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
                    disabled={!!pendingRowBookingId}
                    onClick={() => onChangeMode("edit", row.bookingId)}
                    onMouseEnter={() => prefetchEditForm(row.bookingId)}
                    onFocus={() => prefetchEditForm(row.bookingId)}
                    onPointerDown={() => prefetchEditForm(row.bookingId)}
                  >
                    <EditIcon />
                  </IconButton>
                  <IconButton
                    label="Detach booking"
                    variant="inline"
                    onClick={() => void handleDetach(row.bookingId)}
                    loading={pendingRowBookingId === row.bookingId && pendingRowKind === "unlink"}
                    disabled={!!pendingRowBookingId}
                  >
                    <DetachIcon />
                  </IconButton>
                  <IconButton
                    label="Delete booking"
                    tone="danger"
                    variant="inline"
                    onClick={() => void handleDelete(row.bookingId)}
                    loading={pendingRowBookingId === row.bookingId && pendingRowKind === "delete"}
                    disabled={!!pendingRowBookingId}
                  >
                    <DeleteIcon />
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
