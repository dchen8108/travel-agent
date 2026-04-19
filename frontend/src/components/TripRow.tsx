import { useEffect, useRef, useState } from "react";

import type { TripRow as TripRowValue } from "../types";
import { OfferBlock } from "./OfferBlock";
import { TrackerPreviewPopover } from "./TrackerPreviewPopover";
import { TripIdentityRow } from "./TripIdentityRow";

interface Props {
  row: TripRowValue;
  onOpenBookings: (tripInstanceId: string, mode: "list" | "create", bookingId?: string) => void;
  onOpenTrackers: (tripInstanceId: string) => void;
  onDelete: (row: TripRowValue) => void;
  supportsTrackerPreview?: boolean;
  supportsTrackerHover?: boolean;
  onPrefetchBookings?: (tripInstanceId: string) => void;
  onPrefetchCreateBooking?: (tripInstanceId: string) => void;
  onPrefetchTrackers?: (tripInstanceId: string) => void;
}

export function TripRow({
  row,
  onOpenBookings,
  onOpenTrackers,
  onDelete,
  supportsTrackerPreview = false,
  supportsTrackerHover = false,
  onPrefetchBookings,
  onPrefetchCreateBooking,
  onPrefetchTrackers,
}: Props) {
  const tripInstanceId = row.trip.tripInstanceId;
  const trackerSlotRef = useRef<HTMLDivElement | null>(null);
  const hoverTimerRef = useRef<number | null>(null);
  const [trackerPreviewOpen, setTrackerPreviewOpen] = useState(false);
  const [trackerPreviewPinned, setTrackerPreviewPinned] = useState(false);
  const [previewPlacement, setPreviewPlacement] = useState<"above" | "below">("below");
  const canPreviewTrackers = supportsTrackerPreview && row.actions.showTrackers;

  useEffect(() => () => {
    if (hoverTimerRef.current !== null) {
      window.clearTimeout(hoverTimerRef.current);
    }
  }, []);

  useEffect(() => {
    if (!canPreviewTrackers) {
      setTrackerPreviewOpen(false);
      setTrackerPreviewPinned(false);
    }
  }, [canPreviewTrackers]);

  useEffect(() => {
    if (!trackerPreviewOpen) {
      return;
    }

    function handlePointerDown(event: PointerEvent) {
      const target = event.target;
      if (!(target instanceof Node)) {
        return;
      }
      if (!trackerSlotRef.current?.contains(target)) {
        setTrackerPreviewOpen(false);
        setTrackerPreviewPinned(false);
      }
    }

    function handleEscape(event: KeyboardEvent) {
      if (event.key === "Escape") {
        setTrackerPreviewOpen(false);
        setTrackerPreviewPinned(false);
      }
    }

    window.addEventListener("pointerdown", handlePointerDown);
    window.addEventListener("keydown", handleEscape);
    return () => {
      window.removeEventListener("pointerdown", handlePointerDown);
      window.removeEventListener("keydown", handleEscape);
    };
  }, [trackerPreviewOpen]);

  function clearTrackerPreviewTimer() {
    if (hoverTimerRef.current !== null) {
      window.clearTimeout(hoverTimerRef.current);
      hoverTimerRef.current = null;
    }
  }

  function updatePreviewPlacement() {
    const rect = trackerSlotRef.current?.getBoundingClientRect();
    if (!rect) {
      return;
    }
    const prefersAbove = window.innerHeight - rect.bottom < 320 && rect.top > 320;
    setPreviewPlacement(prefersAbove ? "above" : "below");
  }

  function openTrackerPreview(immediate = false) {
    if (!canPreviewTrackers) {
      return;
    }
    clearTrackerPreviewTimer();
    onPrefetchTrackers?.(tripInstanceId);
    const open = () => {
      updatePreviewPlacement();
      setTrackerPreviewPinned(false);
      setTrackerPreviewOpen(true);
    };
    if (immediate) {
      open();
      return;
    }
    hoverTimerRef.current = window.setTimeout(open, 280);
  }

  function closeTrackerPreview() {
    clearTrackerPreviewTimer();
    if (trackerPreviewPinned) {
      return;
    }
    setTrackerPreviewOpen(false);
  }

  function toggleTrackerPreview() {
    if (!canPreviewTrackers) {
      onOpenTrackers(tripInstanceId);
      return;
    }
    clearTrackerPreviewTimer();
    if (trackerPreviewOpen) {
      if (!trackerPreviewPinned) {
        setTrackerPreviewPinned(true);
        return;
      }
      setTrackerPreviewOpen(false);
      setTrackerPreviewPinned(false);
      return;
    }
    onPrefetchTrackers?.(tripInstanceId);
    updatePreviewPlacement();
    setTrackerPreviewPinned(true);
    setTrackerPreviewOpen(true);
  }

  return (
    <article className="trip-row" id={`scheduled-${tripInstanceId}`}>
      <TripIdentityRow trip={row.trip} onDelete={() => onDelete(row)} />
      {row.bookedOffer ? (
        <OfferBlock
          kind="booked"
          offer={row.bookedOffer}
          onOpen={row.actions.showBookingModal ? () => onOpenBookings(tripInstanceId, "list") : undefined}
          onPrefetchAction={row.actions.showBookingModal ? () => onPrefetchBookings?.(tripInstanceId) : undefined}
        />
      ) : (
        <OfferBlock
          kind="booked"
          offer={{
            label: "",
            detail: "",
            airlineKey: "",
            primaryMetaLabel: "",
            metaBadges: [],
            metaLabel: "",
            priceLabel: "",
            href: "",
            tone: "neutral",
            priceIsStatus: false,
            statusKind: "",
          }}
          emptyState
          onCreate={row.actions.canCreateBooking ? () => onOpenBookings(tripInstanceId, "create") : undefined}
          onPrefetchAction={row.actions.canCreateBooking ? () => onPrefetchCreateBooking?.(tripInstanceId) : undefined}
        />
      )}
      {row.currentOffer ? (
        <div
          ref={trackerSlotRef}
          className={`trip-row__tracker-slot${trackerPreviewOpen ? " is-open" : ""}`}
          onPointerEnter={canPreviewTrackers && supportsTrackerHover ? () => openTrackerPreview(false) : undefined}
          onPointerLeave={canPreviewTrackers && supportsTrackerHover ? closeTrackerPreview : undefined}
          onFocusCapture={canPreviewTrackers ? () => openTrackerPreview(true) : undefined}
          onBlurCapture={canPreviewTrackers ? (event) => {
            const relatedTarget = event.relatedTarget;
            if (!(relatedTarget instanceof Node) || !event.currentTarget.contains(relatedTarget)) {
              setTrackerPreviewOpen(false);
              setTrackerPreviewPinned(false);
            }
          } : undefined}
        >
          <OfferBlock
            kind="live"
            offer={row.currentOffer}
            onOpen={row.actions.showTrackers ? toggleTrackerPreview : undefined}
            onPrefetchAction={row.actions.showTrackers ? () => onPrefetchTrackers?.(tripInstanceId) : undefined}
          />
          {trackerPreviewOpen ? (
            <TrackerPreviewPopover
              tripInstanceId={tripInstanceId}
              currentOffer={row.currentOffer}
              placement={previewPlacement}
            />
          ) : null}
        </div>
      ) : null}
    </article>
  );
}
