import type { CSSProperties } from "react";

const MINUTES_PER_DAY = 24 * 60;
const DEFAULT_START_MINUTES = 6 * 60;
const DEFAULT_END_MINUTES = 10 * 60;

interface Props {
  label: string;
  startTime: string;
  endTime: string;
  onChange: (next: { startTime: string; endTime: string }) => void;
  disabled?: boolean;
}

function parseMinutes(value: string): number | null {
  if (!value || !/^\d{2}:\d{2}$/.test(value)) {
    return null;
  }
  const [hours, minutes] = value.split(":").map(Number);
  if (!Number.isFinite(hours) || !Number.isFinite(minutes)) {
    return null;
  }
  return (hours * 60) + minutes;
}

function formatTime(minutes: number): string {
  const clamped = Math.max(0, Math.min((MINUTES_PER_DAY - 1), minutes));
  const hours = Math.floor(clamped / 60);
  const mins = clamped % 60;
  const meridiem = hours >= 12 ? "PM" : "AM";
  const hour12 = hours % 12 || 12;
  return `${hour12}:${mins.toString().padStart(2, "0")} ${meridiem}`;
}

function toTimeValue(minutes: number): string {
  const clamped = Math.max(0, Math.min((MINUTES_PER_DAY - 1), minutes));
  const hours = Math.floor(clamped / 60);
  const mins = clamped % 60;
  return `${hours.toString().padStart(2, "0")}:${mins.toString().padStart(2, "0")}`;
}

export function TimeRangeField({ label, startTime, endTime, onChange, disabled = false }: Props) {
  const parsedStart = parseMinutes(startTime);
  const parsedEnd = parseMinutes(endTime);
  const isUnset = parsedStart === null || parsedEnd === null;
  const startMinutes = parsedStart ?? DEFAULT_START_MINUTES;
  const endMinutes = parsedEnd ?? DEFAULT_END_MINUTES;
  const safeStart = Math.min(startMinutes, Math.max(0, endMinutes - 1));
  const safeEnd = Math.max(endMinutes, safeStart + 1);
  const startPercent = (safeStart / (MINUTES_PER_DAY - 1)) * 100;
  const endPercent = (safeEnd / (MINUTES_PER_DAY - 1)) * 100;

  function updateRange(nextStart: number, nextEnd: number) {
    const clampedStart = Math.max(0, Math.min(nextStart, nextEnd - 1));
    const clampedEnd = Math.min((MINUTES_PER_DAY - 1), Math.max(nextEnd, clampedStart + 1));
    onChange({
      startTime: toTimeValue(clampedStart),
      endTime: toTimeValue(clampedEnd),
    });
  }

  return (
    <div className="field-block field-block--full">
      <span>{label}</span>
      <div
        className={`time-range-field${isUnset ? " is-unset" : ""}${disabled ? " is-disabled" : ""}`}
        style={
          {
            "--range-start": `${startPercent}%`,
            "--range-end": `${endPercent}%`,
          } as CSSProperties
        }
      >
        <div className="time-range-field__summary">
          <strong>{`${formatTime(safeStart)} – ${formatTime(safeEnd)}`}</strong>
          <small>{isUnset ? "Choose a departure window." : "Departure window"}</small>
        </div>
        <div className="time-range-field__slider">
          <div className="time-range-field__track" aria-hidden="true" />
          <input
            className="time-range-field__input time-range-field__input--start"
            type="range"
            min={0}
            max={MINUTES_PER_DAY - 1}
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
            max={MINUTES_PER_DAY - 1}
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
          <span>11:45 PM</span>
        </div>
      </div>
    </div>
  );
}
