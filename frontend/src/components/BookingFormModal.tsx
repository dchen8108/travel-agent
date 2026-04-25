import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";

import { api } from "../lib/api";
import { bookingFormQueryKey, bookingFormQueryPrefix, bookingPanelQueryKey } from "../lib/queryKeys";
import type { BookingPanelPayload } from "../types";
import { BookingForm } from "./BookingForm";
import { Modal } from "./Modal";
import { useToast } from "./ToastProvider";
import { TripIdentityRow } from "./TripIdentityRow";

interface Props {
  tripInstanceId: string;
  mode: "create" | "edit";
  bookingId: string;
  dashboardFilters: URLSearchParams;
  onClose: () => void;
  onComplete: (panel: BookingPanelPayload | null) => void;
  onRefreshDashboard: () => Promise<void>;
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
    stops: "",
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
  onComplete,
  onRefreshDashboard,
}: Props) {
  const queryClient = useQueryClient();
  const { pushToast } = useToast();
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
    onSuccess: async (result) => {
      if (result.panel) {
        queryClient.setQueryData(bookingPanelQueryKey(tripInstanceId), result.panel);
      }
      await onRefreshDashboard();
      queryClient.removeQueries({ queryKey: bookingFormQueryPrefix(tripInstanceId) });
      pushToast({ message: mode === "edit" ? "Booking saved" : "Booking created" });
      onComplete(result.panel);
    },
  });

  return (
    <Modal title={mode === "edit" ? "Edit booking" : "Create booking"} onClose={onClose} size="panel">
      {formQuery.isError ? (
        <div className="modal-loading">{errorMessage(formQuery.error, "Unable to load booking.")}</div>
      ) : !formQuery.data?.form || !formQuery.data.catalogs ? (
        <div className="modal-loading">Loading booking form…</div>
      ) : (
        <div className="modal-panel-stack">
          <TripIdentityRow trip={formQuery.data.trip} showEditAction={false} />
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
