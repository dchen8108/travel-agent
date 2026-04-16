import type { Offer } from "../types";
import { AddIcon, RefreshIcon, ViewIcon } from "./Icons";
import { IconButton } from "./IconButton";

interface Props {
  offer: Offer;
  kind: "booked" | "live";
  onOpen?: () => void;
  emptyState?: boolean;
  onCreate?: () => void;
}

export function OfferBlock({ offer, kind, onOpen, emptyState = false, onCreate }: Props) {
  if (emptyState) {
    return (
      <div className="offer-block offer-block--empty">
        <div className="offer-block__body">
          <span className="offer-block__placeholder">No bookings attached</span>
          {onCreate ? (
            <IconButton label="Create booking" onClick={onCreate}>
              <AddIcon />
            </IconButton>
          ) : null}
        </div>
      </div>
    );
  }

  return (
    <div className={`offer-block offer-block--${kind}`}>
      <div className="offer-block__body">
        <div className="offer-block__copy">
          <span className="offer-block__label">{offer.label}</span>
          <strong className="offer-block__detail">{offer.detail}</strong>
          <div className="offer-block__meta-row">
            <span className="offer-block__meta">{offer.metaLabel}</span>
            {offer.dayDeltaLabel ? <span className="offer-block__delta">{offer.dayDeltaLabel}</span> : null}
          </div>
        </div>
        <div className="offer-block__price-column">
          {offer.priceIsStatus && offer.statusKind === "pending" ? (
            <span className="offer-block__status-icon"><RefreshIcon /></span>
          ) : (
            <strong className={`offer-block__price offer-block__price--${offer.tone}`}>{offer.priceLabel}</strong>
          )}
        </div>
        {onOpen ? (
          <IconButton label={kind === "booked" ? "View bookings" : "View trackers"} onClick={onOpen}>
            <ViewIcon />
          </IconButton>
        ) : null}
      </div>
    </div>
  );
}
