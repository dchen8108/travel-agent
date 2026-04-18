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
          <span className="offer-block__placeholder">Not booked</span>
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

  const actionContent = actions ?? (onOpen ? (
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
  ) : null);

  const offerMain = (
    <>
      <div className="offer-block__copy">
        <div className="offer-block__label-row">
          <span className="offer-block__label">{offer.label}</span>
          {offer.dayDeltaLabel ? <span className="offer-block__delta">{offer.dayDeltaLabel}</span> : null}
        </div>
        <strong className="offer-block__detail">{offer.detail}</strong>
        {offer.primaryMetaLabel ? (
          <div className="offer-block__primary-meta-row">
            <span className="offer-block__primary-meta">{offer.primaryMetaLabel}</span>
          </div>
        ) : null}
        {offer.metaBadges.length ? (
          <div className="offer-block__badge-row">
            {offer.metaBadges.map((badge) => (
              <span key={badge} className="offer-block__badge">{badge}</span>
            ))}
          </div>
        ) : null}
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
      <div className={`offer-block__body${actionContent ? " offer-block__body--with-action" : ""}`}>
        {offer.href ? (
          <a
            className="offer-block__content offer-block__content--link"
            href={offer.href}
            target="_blank"
            rel="noreferrer"
            aria-label={`Open ${offer.detail} in Google Flights`}
          >
            {offerMain}
          </a>
        ) : (
          <div className="offer-block__content">{offerMain}</div>
        )}
        {actionContent ? <div className="offer-block__actions">{actionContent}</div> : null}
      </div>
    </div>
  );
}
