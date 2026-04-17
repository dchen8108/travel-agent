import type { ReactNode } from "react";

import type { Offer } from "../types";
import { AddIcon, RefreshIcon, ViewIcon } from "./Icons";
import { IconButton } from "./IconButton";

interface Props {
  offer: Offer;
  kind: "booked" | "live";
  onOpen?: () => void;
  emptyState?: boolean;
  onCreate?: () => void;
  onPrefetchAction?: () => void;
  actions?: ReactNode;
}

export function OfferBlock({ offer, kind, onOpen, emptyState = false, onCreate, onPrefetchAction, actions }: Props) {
  if (emptyState) {
    return (
      <div className="offer-block offer-block--empty">
        <div className="offer-block__body">
          <span className="offer-block__placeholder">No bookings attached</span>
          {onCreate ? (
            <IconButton
              label="Create booking"
              variant="inline"
              onClick={onCreate}
              onMouseEnter={onPrefetchAction}
              onFocus={onPrefetchAction}
              onPointerDown={onPrefetchAction}
            >
              <AddIcon />
            </IconButton>
          ) : null}
        </div>
      </div>
    );
  }

  const offerContent = (
    <>
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
    </>
  );

  return (
    <div className={`offer-block offer-block--${kind}`}>
      <div className={`offer-block__body${onOpen || actions ? " offer-block__body--with-action" : ""}`}>
        {offer.href ? (
          <a
            className="offer-block__content offer-block__content--link"
            href={offer.href}
            target="_blank"
            rel="noreferrer"
            aria-label={`Open ${offer.detail} in Google Flights`}
          >
            {offerContent}
          </a>
        ) : (
          <div className="offer-block__content">{offerContent}</div>
        )}
        {actions ? actions : onOpen ? (
          <IconButton
            label={kind === "booked" ? "View bookings" : "View trackers"}
            variant="inline"
            onClick={onOpen}
            onMouseEnter={onPrefetchAction}
            onFocus={onPrefetchAction}
            onPointerDown={onPrefetchAction}
          >
            <ViewIcon />
          </IconButton>
        ) : null}
      </div>
    </div>
  );
}
