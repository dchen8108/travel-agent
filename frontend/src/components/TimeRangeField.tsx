import { useEffect, useRef, useState, type CSSProperties, type KeyboardEvent, type PointerEvent as ReactPointerEvent } from "react";

const SLOT_MINUTES = 30;
const MAX_SLOT = 48;
const DEFAULT_START_SLOT = 0;
const DEFAULT_END_SLOT = MAX_SLOT;
const VALUE_SIZER_LABEL = "11:30 PM – 12:00 AM";

interface Props {
  label: string;
  startTime: string;
  endTime: string;
  onChange: (next: { startTime: string; endTime: string }) => void;
  disabled?: boolean;
}

type HandleName = "start" | "end";

function parseSlot(value: string): number | null {
  if (!value || !/^\d{2}:\d{2}$/.test(value)) {
    return null;
  }
  const [hours, minutes] = value.split(":").map(Number);
  if (!Number.isFinite(hours) || !Number.isFinite(minutes)) {
    return null;
  }
  const totalMinutes = (hours * 60) + minutes;
  if (totalMinutes >= ((23 * 60) + 45)) {
    return MAX_SLOT;
  }
  return Math.round(totalMinutes / SLOT_MINUTES);
}

function slotToMinutes(slot: number): number {
  if (slot >= MAX_SLOT) {
    return (23 * 60) + 59;
  }
  return slot * SLOT_MINUTES;
}

function toTimeValue(slot: number): string {
  const minutes = slotToMinutes(slot);
  const hours = Math.floor(minutes / 60);
  const mins = minutes % 60;
  return `${hours.toString().padStart(2, "0")}:${mins.toString().padStart(2, "0")}`;
}

function formatTime(minutes: number): string {
  const clamped = Math.max(0, Math.min(((23 * 60) + 59), minutes));
  const hours = Math.floor(clamped / 60);
  const mins = clamped % 60;
  const meridiem = hours >= 12 ? "PM" : "AM";
  const hour12 = hours % 12 || 12;
  return `${hour12}:${mins.toString().padStart(2, "0")} ${meridiem}`;
}

function formatSlot(slot: number): string {
  if (slot >= MAX_SLOT) {
    return "12:00 AM";
  }
  return formatTime(slotToMinutes(slot));
}

function clampSlot(slot: number): number {
  return Math.max(0, Math.min(MAX_SLOT, slot));
}

export function TimeRangeField({ label, startTime, endTime, onChange, disabled = false }: Props) {
  const railRef = useRef<HTMLDivElement | null>(null);
  const [draggingHandle, setDraggingHandle] = useState<HandleName | null>(null);
  const parsedStart = parseSlot(startTime);
  const parsedEnd = parseSlot(endTime);
  const startSlot = parsedStart ?? DEFAULT_START_SLOT;
  const endSlot = parsedEnd ?? DEFAULT_END_SLOT;
  const safeStart = Math.min(startSlot, Math.max(0, endSlot - 1));
  const safeEnd = Math.max(endSlot, safeStart + 1);
  const isAnytime = safeStart === DEFAULT_START_SLOT && safeEnd === DEFAULT_END_SLOT;
  const startPercent = (safeStart / MAX_SLOT) * 100;
  const endPercent = (safeEnd / MAX_SLOT) * 100;

  function updateRange(nextStart: number, nextEnd: number) {
    const clampedStart = Math.max(0, Math.min(clampSlot(nextStart), clampSlot(nextEnd) - 1));
    const clampedEnd = Math.min(MAX_SLOT, Math.max(clampSlot(nextEnd), clampedStart + 1));
    onChange({
      startTime: toTimeValue(clampedStart),
      endTime: toTimeValue(clampedEnd),
    });
  }

  function slotFromClientX(clientX: number): number | null {
    const rail = railRef.current;
    if (!rail) {
      return null;
    }
    const rect = rail.getBoundingClientRect();
    if (rect.width <= 0) {
      return null;
    }
    const relativeX = Math.max(0, Math.min(clientX - rect.left, rect.width));
    const ratio = relativeX / rect.width;
    return Math.round(ratio * MAX_SLOT);
  }

  function applyHandleMove(handle: HandleName, slot: number) {
    if (handle === "start") {
      updateRange(slot, safeEnd);
      return;
    }
    updateRange(safeStart, slot);
  }

  function beginDrag(handle: HandleName, event: ReactPointerEvent<HTMLButtonElement>) {
    if (disabled) {
      return;
    }
    event.preventDefault();
    setDraggingHandle(handle);
  }

  function handleRailPointerDown(event: ReactPointerEvent<HTMLDivElement>) {
    if (disabled) {
      return;
    }
    if (event.target instanceof HTMLElement && event.target.closest("button")) {
      return;
    }
    const slot = slotFromClientX(event.clientX);
    if (slot == null) {
      return;
    }
    const targetHandle: HandleName = Math.abs(slot - safeStart) <= Math.abs(slot - safeEnd) ? "start" : "end";
    applyHandleMove(targetHandle, slot);
    setDraggingHandle(targetHandle);
  }

  function nudgeHandle(handle: HandleName, delta: number) {
    if (handle === "start") {
      updateRange(safeStart + delta, safeEnd);
      return;
    }
    updateRange(safeStart, safeEnd + delta);
  }

  function handleSliderKeyDown(handle: HandleName, event: KeyboardEvent<HTMLButtonElement>) {
    if (disabled) {
      return;
    }
    switch (event.key) {
      case "ArrowLeft":
      case "ArrowDown":
        event.preventDefault();
        nudgeHandle(handle, -1);
        break;
      case "ArrowRight":
      case "ArrowUp":
        event.preventDefault();
        nudgeHandle(handle, 1);
        break;
      case "Home":
        event.preventDefault();
        if (handle === "start") {
          updateRange(DEFAULT_START_SLOT, safeEnd);
        } else {
          updateRange(safeStart, safeStart + 1);
        }
        break;
      case "End":
        event.preventDefault();
        if (handle === "start") {
          updateRange(safeEnd - 1, safeEnd);
        } else {
          updateRange(safeStart, DEFAULT_END_SLOT);
        }
        break;
      default:
        break;
    }
  }

  useEffect(() => {
    if (!draggingHandle || disabled) {
      return;
    }
    const activeHandle = draggingHandle;
    function handlePointerMove(event: PointerEvent) {
      const slot = slotFromClientX(event.clientX);
      if (slot == null) {
        return;
      }
      applyHandleMove(activeHandle, slot);
    }
    function stopDrag() {
      setDraggingHandle(null);
    }
    window.addEventListener("pointermove", handlePointerMove);
    window.addEventListener("pointerup", stopDrag);
    window.addEventListener("pointercancel", stopDrag);
    return () => {
      window.removeEventListener("pointermove", handlePointerMove);
      window.removeEventListener("pointerup", stopDrag);
      window.removeEventListener("pointercancel", stopDrag);
    };
  }, [disabled, draggingHandle, safeEnd, safeStart]);

  return (
    <div className="field-block">
      <span>{label}</span>
      <div
        className={`time-range-field${disabled ? " is-disabled" : ""}`}
        style={
          {
            "--range-start": `${startPercent}%`,
            "--range-end": `${endPercent}%`,
          } as CSSProperties
        }
      >
        <div className="time-range-field__value-wrap">
          <span className="time-range-field__value-sizer" aria-hidden="true">{VALUE_SIZER_LABEL}</span>
          <strong className="time-range-field__value">{isAnytime ? "Anytime" : `${formatSlot(safeStart)} – ${formatSlot(safeEnd)}`}</strong>
        </div>
        <div className="time-range-field__slider">
          <div
            ref={railRef}
            className="time-range-field__rail"
            onPointerDown={handleRailPointerDown}
            aria-hidden="true"
          >
            <div className="time-range-field__track" />
            <div className="time-range-field__selection" />
            <button
              type="button"
              className="time-range-field__handle"
              style={{ left: `${startPercent}%` }}
              onPointerDown={(event) => beginDrag("start", event)}
              onKeyDown={(event) => handleSliderKeyDown("start", event)}
              disabled={disabled}
              role="slider"
              aria-label={`${label} start`}
              aria-valuemin={DEFAULT_START_SLOT}
              aria-valuemax={safeEnd - 1}
              aria-valuenow={safeStart}
              aria-valuetext={formatSlot(safeStart)}
            />
            <button
              type="button"
              className="time-range-field__handle"
              style={{ left: `${endPercent}%` }}
              onPointerDown={(event) => beginDrag("end", event)}
              onKeyDown={(event) => handleSliderKeyDown("end", event)}
              disabled={disabled}
              role="slider"
              aria-label={`${label} end`}
              aria-valuemin={safeStart + 1}
              aria-valuemax={DEFAULT_END_SLOT}
              aria-valuenow={safeEnd}
              aria-valuetext={formatSlot(safeEnd)}
            />
          </div>
        </div>
      </div>
    </div>
  );
}
