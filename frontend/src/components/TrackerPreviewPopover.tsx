import type { PointerEventHandler, RefObject } from "react";
import { useQuery } from "@tanstack/react-query";
import { useMemo } from "react";

import { api } from "../lib/api";
import { trackerPanelQueryKey } from "../lib/queryKeys";
import type { Offer } from "../types";
import { OfferBlock } from "./OfferBlock";

interface Props {
  tripInstanceId: string;
  currentOffer: Offer | null;
  placement: "above" | "below";
  popoverRef?: RefObject<HTMLDivElement | null>;
  onPointerEnter?: PointerEventHandler<HTMLDivElement>;
  onPointerLeave?: PointerEventHandler<HTMLDivElement>;
}

function offersMatch(left: Offer | null, right: Offer | null) {
  if (!left || !right) {
    return false;
  }
  return (
    left.detail === right.detail
    && left.primaryMetaLabel === right.primaryMetaLabel
    && left.priceLabel === right.priceLabel
    && left.href === right.href
    && left.airlineKey === right.airlineKey
  );
}

export function TrackerPreviewPopover({
  tripInstanceId,
  currentOffer,
  placement,
  popoverRef,
  onPointerEnter,
  onPointerLeave,
}: Props) {
  const panelQuery = useQuery({
    queryKey: trackerPanelQueryKey(tripInstanceId),
    queryFn: () => api.trackerPanel(tripInstanceId),
  });

  const rows = useMemo(() => {
    const allRows = panelQuery.data?.rows ?? [];
    const hasCurrentMatch = currentOffer ? allRows.some((row) => offersMatch(row.offer, currentOffer)) : false;
    if (hasCurrentMatch) {
      return allRows.filter((row) => !offersMatch(row.offer, currentOffer));
    }
    return allRows;
  }, [currentOffer, panelQuery.data?.rows]);

  return (
    <div
      ref={popoverRef}
      className={`tracker-popover tracker-popover--${placement}`}
      role="group"
      aria-label="Other live fares"
      onPointerEnter={onPointerEnter}
      onPointerLeave={onPointerLeave}
    >
      <div className="tracker-popover__header">
        <strong>{currentOffer ? "Other live fares" : "Live fares"}</strong>
        {panelQuery.data?.lastRefreshLabel ? (
          <span>{panelQuery.data.lastRefreshLabel}</span>
        ) : null}
      </div>
      {panelQuery.isError ? (
        <div className="tracker-popover__empty">
          {panelQuery.error instanceof Error ? panelQuery.error.message : "Unable to load live fares."}
        </div>
      ) : panelQuery.isPending && !panelQuery.data ? (
        <div className="tracker-popover__empty">Loading live fares…</div>
      ) : rows.length ? (
        <div className="tracker-popover__list">
          {rows.map((row) => (
            <article key={row.rowId} className="tracker-popover__row">
              <OfferBlock kind="live" offer={row.offer} />
            </article>
          ))}
        </div>
      ) : (
        <div className="tracker-popover__empty">No other live fares right now.</div>
      )}
    </div>
  );
}
