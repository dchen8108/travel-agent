import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";

import { api } from "../lib/api";
import type { BookingPanelPayload } from "../types";
import { DeleteIcon, DetachIcon, EditIcon } from "./Icons";
import { IconButton } from "./IconButton";
import { Modal } from "./Modal";
import { OfferBlock } from "./OfferBlock";
import { BookingForm } from "./BookingForm";
import { TripIdentityRow } from "./TripIdentityRow";

interface Props {
  tripInstanceId: string;
  mode: "list" | "create" | "edit";
  bookingId: string;
  onClose: () => void;
  onChangeMode: (mode: "list" | "create" | "edit", bookingId?: string) => void;
}

export function BookingPanel({ tripInstanceId, mode, bookingId, onClose, onChangeMode }: Props) {
  const queryClient = useQueryClient();
  const panelQuery = useQuery({
    queryKey: ["booking-panel", tripInstanceId, mode, bookingId],
    queryFn: () => api.bookingPanel(tripInstanceId, mode, bookingId),
  });

  const saveMutation = useMutation({
    mutationFn: async (values: Record<string, string>) => {
      if (mode === "edit" && values.bookingId) {
        return api.updateBooking(values.bookingId, values);
      }
      return api.createBooking(values);
    },
    onSuccess: async () => {
      await queryClient.invalidateQueries({ queryKey: ["dashboard"] });
      await queryClient.invalidateQueries({ queryKey: ["booking-panel", tripInstanceId] });
      onChangeMode("list");
    },
  });

  const rowMutation = useMutation({
    mutationFn: async ({ bookingId: rowBookingId, kind }: { bookingId: string; kind: "delete" | "unlink" }) => {
      if (kind === "delete") {
        await api.deleteBooking(rowBookingId);
      } else {
        await api.unlinkBooking(rowBookingId);
      }
    },
    onSuccess: async () => {
      await queryClient.invalidateQueries({ queryKey: ["dashboard"] });
      await queryClient.invalidateQueries({ queryKey: ["booking-panel", tripInstanceId] });
      onChangeMode("list");
    },
  });

  const payload = panelQuery.data;

  async function handleDelete(bookingIdToDelete: string) {
    if (!window.confirm("Delete this booking?")) {
      return;
    }
    await rowMutation.mutateAsync({ bookingId: bookingIdToDelete, kind: "delete" });
  }

  async function handleDetach(bookingIdToUnlink: string) {
    if (!window.confirm("Detach this booking from the trip?")) {
      return;
    }
    await rowMutation.mutateAsync({ bookingId: bookingIdToUnlink, kind: "unlink" });
  }

  return (
    <Modal title="Bookings" onClose={onClose}>
      {panelQuery.isError ? (
        <div className="modal-loading">{panelQuery.error instanceof Error ? panelQuery.error.message : "Unable to load bookings."}</div>
      ) : panelQuery.isLoading || !payload ? (
        <div className="modal-loading">Loading bookings…</div>
      ) : (
        <BookingPanelContent
          payload={payload}
          mode={mode}
          onClose={onClose}
          onChangeMode={onChangeMode}
          onSave={async (values) => saveMutation.mutateAsync(values)}
          onDelete={handleDelete}
          onDetach={handleDetach}
        />
      )}
    </Modal>
  );
}

function BookingPanelContent({
  payload,
  mode,
  onChangeMode,
  onSave,
  onDelete,
  onDetach,
}: {
  payload: BookingPanelPayload;
  mode: "list" | "create" | "edit";
  onClose: () => void;
  onChangeMode: (mode: "list" | "create" | "edit", bookingId?: string) => void;
  onSave: (values: Record<string, string>) => Promise<unknown>;
  onDelete: (bookingId: string) => Promise<void>;
  onDetach: (bookingId: string) => Promise<void>;
}) {
  return (
    <div className="modal-panel-stack">
      <div className="modal-panel-head">
        <TripIdentityRow trip={payload.trip} />
        {mode === "list" ? (
          <button type="button" className="primary-button" onClick={() => onChangeMode("create")}>
            Create booking
          </button>
        ) : null}
      </div>
      {payload.form ? (
        <BookingForm
          initialValues={payload.form.values}
          catalogs={payload.catalogs}
          submitLabel={payload.form.submitLabel}
          onSubmit={onSave}
          onCancel={() => onChangeMode("list")}
        />
      ) : null}
      <div className="modal-list">
        {payload.rows.map((row) => (
          <article key={row.bookingId} className="modal-list-row">
            <OfferBlock kind="booked" offer={row.offer} />
            <div className="modal-list-row__actions">
              <IconButton label="Edit booking" onClick={() => onChangeMode("edit", row.bookingId)}>
                <EditIcon />
              </IconButton>
              <IconButton label="Detach booking" onClick={() => onDetach(row.bookingId)}>
                <DetachIcon />
              </IconButton>
              <IconButton label="Delete booking" tone="danger" onClick={() => onDelete(row.bookingId)}>
                <DeleteIcon />
              </IconButton>
            </div>
            {row.warning ? <p className="modal-row-warning">{row.warning}</p> : null}
          </article>
        ))}
      </div>
    </div>
  );
}
