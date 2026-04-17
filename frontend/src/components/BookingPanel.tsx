import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";

import { api } from "../lib/api";
import { bookingFormQueryKey, bookingPanelQueryKey } from "../lib/queryKeys";
import type { BookingFormPayload, BookingPanelPayload, DashboardPayload } from "../types";
import { useConfirm } from "./ConfirmProvider";
import { DeleteIcon, DetachIcon, EditIcon } from "./Icons";
import { IconButton } from "./IconButton";
import { Modal } from "./Modal";
import { OfferBlock } from "./OfferBlock";
import { BookingForm } from "./BookingForm";
import { useToast } from "./ToastProvider";
import { TripIdentityRow } from "./TripIdentityRow";

interface Props {
  tripInstanceId: string;
  mode: "list" | "create" | "edit";
  bookingId: string;
  dashboardFilters: URLSearchParams;
  onClose: () => void;
  onReplaceDashboard: (payload: DashboardPayload) => void;
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

function errorMessage(error: unknown, fallback: string) {
  return error instanceof Error ? error.message : fallback;
}

export function BookingPanel({
  tripInstanceId,
  mode,
  bookingId,
  dashboardFilters,
  onClose,
  onReplaceDashboard,
  onChangeMode,
}: Props) {
  const queryClient = useQueryClient();
  const { pushToast } = useToast();
  const { confirm } = useConfirm();
  const listQuery = useQuery({
    queryKey: bookingPanelQueryKey(tripInstanceId),
    queryFn: () => api.bookingPanel(tripInstanceId),
  });
  const formQuery = useQuery({
    queryKey: bookingFormQueryKey(tripInstanceId, mode === "edit" ? bookingId : ""),
    queryFn: () => api.bookingForm(tripInstanceId, mode === "edit" ? bookingId : ""),
    enabled: mode !== "list",
  });

  const saveMutation = useMutation({
    mutationFn: async (values: Record<string, string>) => {
      if (mode === "edit" && values.bookingId) {
        return api.updateBooking(values.bookingId, values, dashboardFilters);
      }
      return api.createBooking(values, dashboardFilters);
    },
    onSuccess: (result) => {
      if (result.panel) {
        queryClient.setQueryData(bookingPanelQueryKey(tripInstanceId), result.panel);
      }
      onReplaceDashboard(result.dashboard);
      queryClient.removeQueries({ queryKey: ["booking-form", tripInstanceId] });
      onChangeMode("list");
      pushToast({ message: mode === "edit" ? "Booking saved" : "Booking created" });
    },
  });

  const rowMutation = useMutation({
    mutationFn: async ({ bookingId: rowBookingId, kind }: { bookingId: string; kind: "delete" | "unlink" }) => {
      if (kind === "delete") {
        return api.deleteBooking(rowBookingId, dashboardFilters);
      }
      return api.unlinkBooking(rowBookingId, dashboardFilters);
    },
    onSuccess: (result, variables) => {
      if (result.panel) {
        queryClient.setQueryData(bookingPanelQueryKey(tripInstanceId), result.panel);
      }
      onReplaceDashboard(result.dashboard);
      queryClient.removeQueries({ queryKey: ["booking-form", tripInstanceId] });
      onChangeMode("list");
      pushToast({ message: variables.kind === "delete" ? "Booking deleted" : "Booking needs linking" });
    },
  });

  function prefetchCreateForm() {
    queryClient.prefetchQuery({
      queryKey: bookingFormQueryKey(tripInstanceId),
      queryFn: () => api.bookingForm(tripInstanceId),
    });
  }

  function prefetchEditForm(rowBookingId: string) {
    queryClient.prefetchQuery({
      queryKey: bookingFormQueryKey(tripInstanceId, rowBookingId),
      queryFn: () => api.bookingForm(tripInstanceId, rowBookingId),
    });
  }

  async function handleDelete(bookingIdToDelete: string) {
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
      await rowMutation.mutateAsync({ bookingId: bookingIdToDelete, kind: "delete" });
    } catch (error) {
      pushToast({ message: errorMessage(error, "Unable to delete booking."), kind: "error" });
    }
  }

  async function handleDetach(bookingIdToUnlink: string) {
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
      await rowMutation.mutateAsync({ bookingId: bookingIdToUnlink, kind: "unlink" });
    } catch (error) {
      pushToast({ message: errorMessage(error, "Unable to detach booking."), kind: "error" });
    }
  }

  const panelPayload = listQuery.data;
  const formPayload = mode === "list" ? null : formQuery.data;
  const loading = listQuery.isLoading || !panelPayload || (mode !== "list" && (formQuery.isLoading || !formPayload?.form));
  const error =
    (listQuery.isError && (listQuery.error instanceof Error ? listQuery.error.message : "Unable to load bookings."))
    || (mode !== "list" && formQuery.isError && (formQuery.error instanceof Error ? formQuery.error.message : "Unable to load booking."));

  return (
    <Modal title="Bookings" onClose={onClose}>
      {error ? (
        <div className="modal-loading">{error}</div>
      ) : loading ? (
        <div className="modal-loading">Loading bookings…</div>
      ) : (
        <BookingPanelContent
          payload={panelPayload}
          mode={mode}
          formValues={formPayload?.form?.values ?? blankBookingForm(tripInstanceId)}
          formSubmitLabel={formPayload?.form?.submitLabel ?? "Create booking"}
          formCatalogs={formPayload?.catalogs}
          onChangeMode={onChangeMode}
          onSave={async (values) => saveMutation.mutateAsync(values)}
          onDelete={handleDelete}
          onDetach={handleDetach}
          onPrefetchCreate={prefetchCreateForm}
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
  onPrefetchCreate,
  onPrefetchEdit,
}: {
  payload: BookingPanelPayload;
  mode: "list" | "create" | "edit";
  formValues: Record<string, string>;
  formSubmitLabel: string;
  formCatalogs: BookingFormPayload["catalogs"] | undefined;
  onChangeMode: (mode: "list" | "create" | "edit", bookingId?: string) => void;
  onSave: (values: Record<string, string>) => Promise<unknown>;
  onDelete: (bookingId: string) => Promise<void>;
  onDetach: (bookingId: string) => Promise<void>;
  onPrefetchCreate: () => void;
  onPrefetchEdit: (bookingId: string) => void;
}) {
  const showingForm = mode !== "list";

  return (
    <div className="modal-panel-stack">
      <div className="modal-panel-head">
        <TripIdentityRow trip={payload.trip} />
        {mode === "list" ? (
          <button
            type="button"
            className="primary-button"
            onClick={() => onChangeMode("create")}
            onMouseEnter={onPrefetchCreate}
            onFocus={onPrefetchCreate}
            onPointerDown={onPrefetchCreate}
          >
            Create booking
          </button>
        ) : null}
      </div>
      {showingForm ? (
        <BookingForm
          initialValues={formValues}
          catalogs={formCatalogs!}
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
