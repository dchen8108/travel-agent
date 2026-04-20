import type { BookingPanelPayload } from "../types";
import { BookingFormModal } from "./BookingFormModal";
import { BookingInspector } from "./BookingInspector";
import { Modal } from "./Modal";

interface Props {
  tripInstanceId: string;
  mode: "list" | "create" | "edit";
  bookingId: string;
  initialPanel: BookingPanelPayload | null;
  dashboardFilters: URLSearchParams;
  onClose: () => void;
  onRefreshDashboard: () => void;
  onChangeMode: (mode: "list" | "create" | "edit", bookingId?: string) => void;
}

export function BookingPanel({
  tripInstanceId,
  mode,
  bookingId,
  initialPanel,
  dashboardFilters,
  onClose,
  onRefreshDashboard,
  onChangeMode,
}: Props) {
  if (mode !== "list") {
    return (
      <BookingFormModal
        tripInstanceId={tripInstanceId}
        mode={mode}
        bookingId={bookingId}
        dashboardFilters={dashboardFilters}
        onClose={() => onChangeMode("list")}
        onRefreshDashboard={onRefreshDashboard}
      />
    );
  }

  return (
    <Modal title="Bookings" onClose={onClose} size="panel">
      <BookingInspector
        tripInstanceId={tripInstanceId}
        initialPanel={initialPanel}
        dashboardFilters={dashboardFilters}
        onRefreshDashboard={onRefreshDashboard}
        onChangeMode={onChangeMode}
      />
    </Modal>
  );
}
