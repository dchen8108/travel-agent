import { useMutation, useQuery } from "@tanstack/react-query";

import { api } from "../lib/api";
import { unmatchedBookingFormQueryKey } from "../lib/queryKeys";
import { BookingForm } from "./BookingForm";
import { DateTile } from "./DateTile";
import { Modal } from "./Modal";
import { OfferBlock } from "./OfferBlock";
import { useToast } from "./ToastProvider";

interface Props {
  unmatchedBookingId: string;
  dashboardFilters: URLSearchParams;
  onClose: () => void;
  onRefreshDashboard: () => void;
}

function errorMessage(error: unknown, fallback: string) {
  return error instanceof Error ? error.message : fallback;
}

export function UnmatchedBookingEditorModal({
  unmatchedBookingId,
  dashboardFilters,
  onClose,
  onRefreshDashboard,
}: Props) {
  const { pushToast } = useToast();
  const formQuery = useQuery({
    queryKey: unmatchedBookingFormQueryKey(unmatchedBookingId),
    queryFn: () => api.unmatchedBookingForm(unmatchedBookingId),
  });

  const saveMutation = useMutation({
    mutationFn: (values: Record<string, string>) => api.updateUnmatchedBooking(unmatchedBookingId, values, dashboardFilters),
    onSuccess: () => {
      onRefreshDashboard();
      pushToast({ message: "Booking saved" });
      onClose();
    },
  });

  const error =
    formQuery.isError
      ? errorMessage(formQuery.error, "Unable to load booking.")
      : "";

  return (
    <Modal title="Edit booking" onClose={onClose}>
      {error ? (
        <div className="modal-loading">{error}</div>
      ) : formQuery.isLoading || !formQuery.data ? (
        <div className="modal-loading">Loading booking…</div>
      ) : (
        <div className="modal-panel-stack">
          <div className="unmatched-booking-editor__head">
            <DateTile tile={formQuery.data.dateTile} />
            <div className="unmatched-booking-editor__offer">
              <OfferBlock kind="booked" offer={formQuery.data.offer} />
            </div>
          </div>
          <BookingForm
            initialValues={formQuery.data.form.values}
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
