import { useEffect, useLayoutEffect, useRef, useState } from "react";

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
  const trackerReferenceRef = useRef<HTMLDivElement | null>(null);
  const trackerPopoverRef = useRef<HTMLDivElement | null>(null);
  const hoverTimerRef = useRef<number | null>(null);
  const closeTimerRef = useRef<number | null>(null);
  const hoverGuardRef = useRef<(() => void) | null>(null);
  const pointerPositionRef = useRef<{ x: number; y: number } | null>(null);
  const [trackerPreviewOpen, setTrackerPreviewOpen] = useState(false);
  const [trackerPreviewPinned, setTrackerPreviewPinned] = useState(false);
  const [previewPlacement, setPreviewPlacement] = useState<"above" | "below">("below");
  const [previewMaxHeight, setPreviewMaxHeight] = useState(0);
  const canPreviewTrackers = supportsTrackerPreview && row.actions.showTrackers;

  useEffect(() => () => {
    if (hoverTimerRef.current !== null) {
      window.clearTimeout(hoverTimerRef.current);
    }
    if (closeTimerRef.current !== null) {
      window.clearTimeout(closeTimerRef.current);
    }
    hoverGuardRef.current?.();
  }, []);

  useEffect(() => {
    if (!canPreviewTrackers) {
      clearTrackerPreviewTimer();
      clearTrackerPreviewCloseTimer();
      clearTrackerPreviewHoverGuard();
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
        clearTrackerPreviewCloseTimer();
        clearTrackerPreviewHoverGuard();
        setTrackerPreviewOpen(false);
        setTrackerPreviewPinned(false);
      }
    }

    function handleEscape(event: KeyboardEvent) {
      if (event.key === "Escape") {
        clearTrackerPreviewCloseTimer();
        clearTrackerPreviewHoverGuard();
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

  function clearTrackerPreviewCloseTimer() {
    if (closeTimerRef.current !== null) {
      window.clearTimeout(closeTimerRef.current);
      closeTimerRef.current = null;
    }
  }

  function clearTrackerPreviewHoverGuard() {
    hoverGuardRef.current?.();
    hoverGuardRef.current = null;
  }

  function updatePreviewPlacement(preferredHeight = 512) {
    const rect = trackerSlotRef.current?.getBoundingClientRect();
    if (!rect) {
      return;
    }
    const viewportMargin = 16;
    const hoverBridge = 12;
    const availableBelow = Math.max(0, window.innerHeight - rect.bottom - viewportMargin - hoverBridge);
    const availableAbove = Math.max(0, rect.top - viewportMargin - hoverBridge);
    const canFitBelow = availableBelow >= preferredHeight;
    const canFitAbove = availableAbove >= preferredHeight;
    const placement = canFitBelow
      ? "below"
      : canFitAbove
        ? "above"
        : availableBelow >= availableAbove
          ? "below"
          : "above";
    const availableHeight = placement === "below" ? availableBelow : availableAbove;
    setPreviewPlacement(placement);
    setPreviewMaxHeight(Math.max(220, Math.floor(availableHeight)));
  }

  useLayoutEffect(() => {
    if (!trackerPreviewOpen) {
      return;
    }

    const measure = () => {
      const popover = trackerPopoverRef.current;
      const preferredHeight = popover ? Math.ceil(popover.scrollHeight) : 512;
      updatePreviewPlacement(preferredHeight);
    };

    measure();

    if (typeof ResizeObserver === "undefined") {
      window.addEventListener("resize", measure);
      return () => {
        window.removeEventListener("resize", measure);
      };
    }

    const observer = new ResizeObserver(() => {
      measure();
    });
    if (trackerPopoverRef.current) {
      observer.observe(trackerPopoverRef.current);
    }
    window.addEventListener("resize", measure);
    return () => {
      observer.disconnect();
      window.removeEventListener("resize", measure);
    };
  }, [trackerPreviewOpen]);

  function openTrackerPreview(immediate = false) {
    if (!canPreviewTrackers) {
      return;
    }
    clearTrackerPreviewTimer();
    clearTrackerPreviewCloseTimer();
    clearTrackerPreviewHoverGuard();
    if (trackerPreviewOpen) {
      return;
    }
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

  function pointerWithinTrackerTransit(clientX: number, clientY: number) {
    const referenceRect = trackerReferenceRef.current?.getBoundingClientRect();
    const popoverRect = trackerPopoverRef.current?.getBoundingClientRect();
    if (!referenceRect || !popoverRect) {
      return false;
    }
    const buffer = 12;
    const left = Math.min(referenceRect.left, popoverRect.left) - buffer;
    const right = Math.max(referenceRect.right, popoverRect.right) + buffer;
    const top = Math.min(referenceRect.top, popoverRect.top) - buffer;
    const bottom = Math.max(referenceRect.bottom, popoverRect.bottom) + buffer;
    return clientX >= left && clientX <= right && clientY >= top && clientY <= bottom;
  }

  function closeTrackerPreview(event?: { clientX: number; clientY: number }) {
    clearTrackerPreviewTimer();
    if (trackerPreviewPinned) {
      return;
    }
    clearTrackerPreviewCloseTimer();
    clearTrackerPreviewHoverGuard();
    if (event) {
      pointerPositionRef.current = { x: event.clientX, y: event.clientY };
    }

    const handlePointerMove = (event: PointerEvent) => {
      pointerPositionRef.current = { x: event.clientX, y: event.clientY };
      if (pointerWithinTrackerTransit(event.clientX, event.clientY)) {
        return;
      }
      clearTrackerPreviewHoverGuard();
      clearTrackerPreviewCloseTimer();
      setTrackerPreviewOpen(false);
    };

    window.addEventListener("pointermove", handlePointerMove);
    hoverGuardRef.current = () => {
      window.removeEventListener("pointermove", handlePointerMove);
    };

    closeTimerRef.current = window.setTimeout(() => {
      const pointerPosition = pointerPositionRef.current;
      if (pointerPosition && pointerWithinTrackerTransit(pointerPosition.x, pointerPosition.y)) {
        closeTimerRef.current = null;
        return;
      }
      clearTrackerPreviewHoverGuard();
      setTrackerPreviewOpen(false);
      closeTimerRef.current = null;
    }, 420);
  }

  function toggleTrackerPreview() {
    if (!canPreviewTrackers) {
      onOpenTrackers(tripInstanceId);
      return;
    }
    clearTrackerPreviewTimer();
    clearTrackerPreviewCloseTimer();
    clearTrackerPreviewHoverGuard();
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
          className={`trip-row__tracker-slot${trackerPreviewOpen ? " is-open" : ""}${trackerPreviewOpen ? ` trip-row__tracker-slot--${previewPlacement}` : ""}`}
          onFocusCapture={canPreviewTrackers ? () => openTrackerPreview(true) : undefined}
          onBlurCapture={canPreviewTrackers ? (event) => {
            const relatedTarget = event.relatedTarget;
            if (!(relatedTarget instanceof Node) || !event.currentTarget.contains(relatedTarget)) {
              clearTrackerPreviewHoverGuard();
              clearTrackerPreviewCloseTimer();
              setTrackerPreviewOpen(false);
              setTrackerPreviewPinned(false);
            }
          } : undefined}
        >
          <div
            ref={trackerReferenceRef}
            onPointerEnter={canPreviewTrackers && supportsTrackerHover ? () => openTrackerPreview(false) : undefined}
            onPointerLeave={canPreviewTrackers && supportsTrackerHover ? (event) => closeTrackerPreview(event) : undefined}
          >
            <OfferBlock
              kind="live"
              offer={row.currentOffer}
              onOpen={row.actions.showTrackers ? toggleTrackerPreview : undefined}
              onPrefetchAction={row.actions.showTrackers ? () => onPrefetchTrackers?.(tripInstanceId) : undefined}
            />
          </div>
          {trackerPreviewOpen ? (
            <TrackerPreviewPopover
              tripInstanceId={tripInstanceId}
              currentOffer={row.currentOffer}
              placement={previewPlacement}
              maxHeight={previewMaxHeight}
              popoverRef={trackerPopoverRef}
              onPointerEnter={canPreviewTrackers && supportsTrackerHover ? () => openTrackerPreview(true) : undefined}
              onPointerLeave={canPreviewTrackers && supportsTrackerHover ? (event) => closeTrackerPreview(event) : undefined}
            />
          ) : null}
        </div>
      ) : null}
    </article>
  );
}
