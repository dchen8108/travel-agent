import type { CSSProperties } from "react";

const SLOT_MINUTES = 30;
const MAX_SLOT = 48;
const DEFAULT_START_SLOT = 0;
const DEFAULT_END_SLOT = MAX_SLOT;

interface Props {
  label: string;
  startTime: string;
  endTime: string;
  onChange: (next: { startTime: string; endTime: string }) => void;
  disabled?: boolean;
}

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

function formatTime(minutes: number): string {
  const clamped = Math.max(0, Math.min(((23 * 60) + 59), minutes));
  const hours = Math.floor(clamped / 60);
  const mins = clamped % 60;
  const meridiem = hours >= 12 ? "PM" : "AM";
  const hour12 = hours % 12 || 12;
  return `${hour12}:${mins.toString().padStart(2, "0")} ${meridiem}`;
}

function slotToMinutes(slot: number): number {
  if (slot >= MAX_SLOT) {
    return (23 * 60) + 59;
  }
  return slot * SLOT_MINUTES;
}

function formatSlot(slot: number): string {
  return formatTime(slotToMinutes(slot));
}

function toTimeValue(slot: number): string {
  const minutes = slotToMinutes(slot);
  const hours = Math.floor(minutes / 60);
  const mins = minutes % 60;
  return `${hours.toString().padStart(2, "0")}:${mins.toString().padStart(2, "0")}`;
}

export function TimeRangeField({ label, startTime, endTime, onChange, disabled = false }: Props) {
  const parsedStart = parseSlot(startTime);
  const parsedEnd = parseSlot(endTime);
  const startSlot = parsedStart ?? DEFAULT_START_SLOT;
  const endSlot = parsedEnd ?? DEFAULT_END_SLOT;
  const safeStart = Math.min(startSlot, Math.max(0, endSlot - 1));
  const safeEnd = Math.max(endSlot, safeStart + 1);
  const startPercent = (safeStart / MAX_SLOT) * 100;
  const endPercent = (safeEnd / MAX_SLOT) * 100;
  const isAnytime = safeStart === DEFAULT_START_SLOT && safeEnd === DEFAULT_END_SLOT;

  function updateRange(nextStart: number, nextEnd: number) {
    const clampedStart = Math.max(0, Math.min(nextStart, nextEnd - 1));
    const clampedEnd = Math.min(MAX_SLOT, Math.max(nextEnd, clampedStart + 1));
    onChange({
      startTime: toTimeValue(clampedStart),
      endTime: toTimeValue(clampedEnd),
    });
  }

  return (
    <div className="field-block field-block--full">
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
        <div className="time-range-field__summary">
          <strong>{isAnytime ? "Anytime" : `${formatSlot(safeStart)} – ${formatSlot(safeEnd)}`}</strong>
          <small>{isAnytime ? "No departure restriction." : "Departure window"}</small>
        </div>
        <div className="time-range-field__slider">
          <div className="time-range-field__track" aria-hidden="true" />
          <input
            className="time-range-field__input time-range-field__input--start"
            type="range"
            min={0}
            max={MAX_SLOT}
            step={1}
            value={safeStart}
            onChange={(event) => updateRange(Number(event.target.value), safeEnd)}
            disabled={disabled}
            aria-label={`${label} start`}
          />
          <input
            className="time-range-field__input time-range-field__input--end"
            type="range"
            min={0}
            max={MAX_SLOT}
            step={1}
            value={safeEnd}
            onChange={(event) => updateRange(safeStart, Number(event.target.value))}
            disabled={disabled}
            aria-label={`${label} end`}
          />
        </div>
        <div className="time-range-field__labels" aria-hidden="true">
          <span>12:00 AM</span>
          <span>12:00 PM</span>
          <span>11:59 PM</span>
        </div>
      </div>
    </div>
  );
}
