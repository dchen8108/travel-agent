import type { TrackerPanelPayload } from "../types";
import { Modal } from "./Modal";
import { TrackerInspector } from "./TrackerInspector";

interface Props {
  tripInstanceId: string;
  initialPanel: TrackerPanelPayload | null;
  onClose: () => void;
}

export function TrackerPanel({ tripInstanceId, initialPanel, onClose }: Props) {
  return (
    <Modal title="Flights" onClose={onClose} size="compact">
      <TrackerInspector tripInstanceId={tripInstanceId} initialPanel={initialPanel} />
    </Modal>
  );
}
