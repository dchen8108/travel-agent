import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";

import { api } from "../lib/api";
import { bookingFormQueryKey, bookingFormQueryPrefix, bookingPanelQueryKey } from "../lib/queryKeys";
import { BookingForm } from "./BookingForm";
import { useConfirm } from "./ConfirmProvider";
import { DeleteIcon, DetachIcon } from "./Icons";
import { IconButton } from "./IconButton";
import { Modal } from "./Modal";
import { useToast } from "./ToastProvider";
import { TripIdentityRow } from "./TripIdentityRow";

interface Props {
  tripInstanceId: string;
  mode: "create" | "edit";
  bookingId: string;
  dashboardFilters: URLSearchParams;
  onClose: () => void;
  onRefreshDashboard: () => void;
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
    arrivalDayOffset: "0",
    fareClass: "basic_economy",
    flightNumber: "",
    bookedPrice: "",
    recordLocator: "",
    notes: "",
  };
}

function errorMessage(error: unknown, fallback: string) {
  return error instanceof Error ? error.message : fallback;
}

export function BookingFormModal({
  tripInstanceId,
  mode,
  bookingId,
  dashboardFilters,
  onClose,
  onRefreshDashboard,
}: Props) {
  const queryClient = useQueryClient();
  const { pushToast } = useToast();
  const { confirm } = useConfirm();
  const formQuery = useQuery({
    queryKey: bookingFormQueryKey(tripInstanceId, mode === "edit" ? bookingId : ""),
    queryFn: () => api.bookingForm(tripInstanceId, mode === "edit" ? bookingId : ""),
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
      onRefreshDashboard();
      queryClient.removeQueries({ queryKey: bookingFormQueryPrefix(tripInstanceId) });
      pushToast({ message: mode === "edit" ? "Booking saved" : "Booking created" });
      onClose();
    },
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
      pushToast({ message: variables.kind === "delete" ? "Booking deleted" : "Booking needs linking" });
      onClose();
    },
  });

  async function handleDelete() {
    if (mode !== "edit" || !bookingId) {
      return;
    }
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

  async function handleDetach() {
    if (mode !== "edit" || !bookingId) {
      return;
    }
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

  return (
    <Modal title={mode === "edit" ? "Edit booking" : "Create booking"} onClose={onClose} size="panel">
      {formQuery.isError ? (
        <div className="modal-loading">{errorMessage(formQuery.error, "Unable to load booking.")}</div>
      ) : !formQuery.data?.form || !formQuery.data.catalogs ? (
        <div className="modal-loading">Loading booking form…</div>
      ) : (
        <div className="modal-panel-stack">
          <TripIdentityRow
            trip={formQuery.data.trip}
            showEditAction={false}
            actions={mode === "edit" ? (
              <>
                <IconButton
                  label="Detach booking"
                  variant="inline"
                  onClick={() => void handleDetach()}
                  loading={rowMutation.isPending && rowMutation.variables?.kind === "unlink"}
                  disabled={saveMutation.isPending}
                >
                  <DetachIcon />
                </IconButton>
                <IconButton
                  label="Delete booking"
                  tone="danger"
                  variant="inline"
                  onClick={() => void handleDelete()}
                  loading={rowMutation.isPending && rowMutation.variables?.kind === "delete"}
                  disabled={saveMutation.isPending}
                >
                  <DeleteIcon />
                </IconButton>
              </>
            ) : null}
          />
          <BookingForm
            initialValues={formQuery.data.form.values ?? blankBookingForm(tripInstanceId)}
            catalogs={formQuery.data.catalogs}
            submitLabel={formQuery.data.form.submitLabel}
            onSubmit={async (values) => saveMutation.mutateAsync(values)}
            onCancel={onClose}
          />
        </div>
      )}
    </Modal>
  );
}
