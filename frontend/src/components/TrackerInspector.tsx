import { useQuery } from "@tanstack/react-query";

import { api } from "../lib/api";
import { trackerPanelQueryKey } from "../lib/queryKeys";
import type { TrackerPanelPayload } from "../types";
import { OfferBlock } from "./OfferBlock";
import { TripIdentityRow } from "./TripIdentityRow";

interface Props {
  tripInstanceId: string;
  initialPanel: TrackerPanelPayload | null;
}

function errorMessage(error: unknown, fallback: string) {
  return error instanceof Error ? error.message : fallback;
}

export function TrackerInspector({ tripInstanceId, initialPanel }: Props) {
  const panelQuery = useQuery({
    queryKey: trackerPanelQueryKey(tripInstanceId),
    queryFn: () => api.trackerPanel(tripInstanceId),
    placeholderData: initialPanel ?? undefined,
  });

  if (panelQuery.isError) {
    return <div className="modal-loading">{errorMessage(panelQuery.error, "Unable to load flights.")}</div>;
  }

  if (!panelQuery.data) {
    return <div className="modal-loading">Loading flights…</div>;
  }

  return (
    <div className="modal-panel-stack">
      <div className="modal-panel-head">
        <TripIdentityRow trip={panelQuery.data.trip} showEditAction={false} />
      </div>
      {panelQuery.data.rows.length ? (
        <div className="modal-list">
          {panelQuery.data.rows.map((row) => (
            <article key={row.rowId} className="modal-list-row modal-list-row--tracker">
              <OfferBlock kind="live" offer={row.offer} />
            </article>
          ))}
        </div>
      ) : (
        <div className="modal-loading">{panelQuery.data.emptyLabel}</div>
      )}
      {panelQuery.data.lastRefreshLabel ? (
        <div className="modal-footer-note">{panelQuery.data.lastRefreshLabel}</div>
      ) : null}
    </div>
  );
}
