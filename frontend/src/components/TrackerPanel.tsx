import { useQuery } from "@tanstack/react-query";

import { api } from "../lib/api";
import { Modal } from "./Modal";
import { OfferBlock } from "./OfferBlock";
import { TripIdentityRow } from "./TripIdentityRow";

interface Props {
  tripInstanceId: string;
  onClose: () => void;
}

export function TrackerPanel({ tripInstanceId, onClose }: Props) {
  const panelQuery = useQuery({
    queryKey: ["tracker-panel", tripInstanceId],
    queryFn: () => api.trackerPanel(tripInstanceId),
  });

  return (
    <Modal title="Trackers" onClose={onClose}>
      {panelQuery.isError ? (
        <div className="modal-loading">{panelQuery.error instanceof Error ? panelQuery.error.message : "Unable to load trackers."}</div>
      ) : panelQuery.isLoading || !panelQuery.data ? (
        <div className="modal-loading">Loading trackers…</div>
      ) : (
        <div className="modal-panel-stack">
          <div className="modal-panel-head">
            <TripIdentityRow trip={panelQuery.data.trip} />
          </div>
          <div className="modal-list">
            {panelQuery.data.rows.map((row) => (
              <article key={row.rowId} className="modal-list-row modal-list-row--tracker">
                <OfferBlock kind="live" offer={row.offer} />
              </article>
            ))}
          </div>
          {panelQuery.data.lastRefreshLabel ? (
            <div className="modal-footer-note">{panelQuery.data.lastRefreshLabel}</div>
          ) : null}
        </div>
      )}
    </Modal>
  );
}
