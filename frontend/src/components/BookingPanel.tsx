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

function blankBookingForm(tripInstanceId: string): Record<string, string> {
  return {
    bookingId: "",
    tripInstanceId,
    airline: "",
    originAirport: "",
    destinationAirport: "",
    departureDate: "",
    departureTime: "",
    arrivalTime: "",
    bookedPrice: "",
    recordLocator: "",
    notes: "",
  };
}

export function BookingPanel({ tripInstanceId, mode, bookingId, onClose, onChangeMode }: Props) {
  const queryClient = useQueryClient();
  const listQuery = useQuery({
    queryKey: ["booking-panel", tripInstanceId],
    queryFn: () => api.bookingPanel(tripInstanceId, "list"),
    placeholderData: (previous) => previous,
  });
  const editQuery = useQuery({
    queryKey: ["booking-form", tripInstanceId, bookingId],
    queryFn: () => api.bookingPanel(tripInstanceId, "edit", bookingId),
    enabled: mode === "edit" && Boolean(bookingId),
  });

  const saveMutation = useMutation({
    mutationFn: async (values: Record<string, string>) => {
      if (mode === "edit" && values.bookingId) {
        return api.updateBooking(values.bookingId, values);
      }
      return api.createBooking(values);
    },
    onSuccess: async (result) => {
      queryClient.setQueryData(["booking-panel", tripInstanceId], result);
      queryClient.removeQueries({ queryKey: ["booking-form", tripInstanceId] });
      await queryClient.invalidateQueries({ queryKey: ["dashboard"] });
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
      queryClient.removeQueries({ queryKey: ["booking-form", tripInstanceId] });
      onChangeMode("list");
    },
  });

  const payload = listQuery.data;
  const formPayload = mode === "edit" ? editQuery.data : payload;

  function prefetchEditForm(rowBookingId: string) {
    queryClient.prefetchQuery({
      queryKey: ["booking-form", tripInstanceId, rowBookingId],
      queryFn: () => api.bookingPanel(tripInstanceId, "edit", rowBookingId),
    });
  }

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

  const loading = listQuery.isLoading || !payload || (mode === "edit" && (editQuery.isLoading || !formPayload?.form));
  const error =
    (listQuery.isError && (listQuery.error instanceof Error ? listQuery.error.message : "Unable to load bookings."))
    || (mode === "edit" && editQuery.isError && (editQuery.error instanceof Error ? editQuery.error.message : "Unable to load booking."));

  return (
    <Modal title="Bookings" onClose={onClose}>
      {error ? (
        <div className="modal-loading">{error}</div>
      ) : loading ? (
        <div className="modal-loading">Loading bookings…</div>
      ) : (
        <BookingPanelContent
          payload={payload}
          mode={mode}
          formValues={mode === "edit" ? formPayload?.form?.values ?? blankBookingForm(tripInstanceId) : blankBookingForm(tripInstanceId)}
          formSubmitLabel={mode === "edit" ? formPayload?.form?.submitLabel ?? "Save booking" : "Create booking"}
          formCatalogs={formPayload?.catalogs ?? payload.catalogs}
          onChangeMode={onChangeMode}
          onSave={async (values) => saveMutation.mutateAsync(values)}
          onDelete={handleDelete}
          onDetach={handleDetach}
          onPrefetchEdit={prefetchEditForm}
        />
      )}
    </Modal>
  );
}

function BookingPanelContent({
  payload,
  mode,
  formValues,
  formSubmitLabel,
  formCatalogs,
  onChangeMode,
  onSave,
  onDelete,
  onDetach,
  onPrefetchEdit,
}: {
  payload: BookingPanelPayload;
  mode: "list" | "create" | "edit";
  formValues: Record<string, string>;
  formSubmitLabel: string;
  formCatalogs: BookingPanelPayload["catalogs"];
  onChangeMode: (mode: "list" | "create" | "edit", bookingId?: string) => void;
  onSave: (values: Record<string, string>) => Promise<unknown>;
  onDelete: (bookingId: string) => Promise<void>;
  onDetach: (bookingId: string) => Promise<void>;
  onPrefetchEdit: (bookingId: string) => void;
}) {
  const showingForm = mode !== "list";

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
      {showingForm ? (
        <BookingForm
          initialValues={formValues}
          catalogs={formCatalogs}
          submitLabel={formSubmitLabel}
          onSubmit={onSave}
          onCancel={() => onChangeMode("list")}
        />
      ) : (
        <div className="modal-list">
          {payload.rows.map((row) => (
            <article key={row.bookingId} className="modal-list-row">
              <OfferBlock kind="booked" offer={row.offer} />
              <div className="modal-list-row__actions">
                <IconButton
                  label="Edit booking"
                  onClick={() => onChangeMode("edit", row.bookingId)}
                  onMouseEnter={() => onPrefetchEdit(row.bookingId)}
                  onFocus={() => onPrefetchEdit(row.bookingId)}
                  onPointerDown={() => onPrefetchEdit(row.bookingId)}
                >
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
      )}
    </div>
  );
}
