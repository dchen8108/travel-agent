import { useEffect, useState } from "react";

import { SearchSelectField } from "./SearchSelectField";

const ARRIVAL_DAY_OPTIONS = [
  { value: "0", label: "Same day" },
  { value: "1", label: "Next day" },
  { value: "2", label: "2 days later" },
];

function validateBooking(values: Record<string, string>) {
  if (!values.originAirport.trim()) {
    return "Choose an origin airport.";
  }
  if (!values.destinationAirport.trim()) {
    return "Choose a destination airport.";
  }
  if (!values.airline.trim()) {
    return "Choose an airline.";
  }
  if (!values.departureDate.trim()) {
    return "Choose a departure date.";
  }
  if (!values.departureTime.trim()) {
    return "Departure time is required.";
  }
  if (!values.bookedPrice.trim()) {
    return "Booked price is required.";
  }
  if (!/^\$?\d+(?:\.\d{1,2})?$/.test(values.bookedPrice.trim())) {
    return "Enter a valid booked price.";
  }
  return "";
}

interface Props {
  initialValues: Record<string, string>;
  catalogs: {
    airports: Array<{ value: string; label: string }>;
    airlines: Array<{ value: string; label: string }>;
    fareClasses: Array<{ value: string; label: string }>;
  };
  submitLabel: string;
  onSubmit: (values: Record<string, string>) => Promise<unknown>;
  onCancel: () => void;
}

export function BookingForm({ initialValues, catalogs, submitLabel, onSubmit, onCancel }: Props) {
  const [values, setValues] = useState<Record<string, string>>(initialValues);
  const [error, setError] = useState("");
  const [submitting, setSubmitting] = useState(false);
  const busyLabel = submitLabel.toLowerCase().includes("create") ? "Creating…" : "Saving…";

  useEffect(() => {
    setValues(initialValues);
  }, [initialValues]);

  function update(key: string, value: string) {
    setValues((current) => ({ ...current, [key]: value }));
  }

  async function handleSubmit(event: React.FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const validationError = validateBooking(values);
    if (validationError) {
      setError(validationError);
      return;
    }
    setSubmitting(true);
    setError("");
    try {
      await onSubmit(values);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Unable to save booking.");
    } finally {
      setSubmitting(false);
    }
  }

  return (
    <form className="booking-form-card" onSubmit={handleSubmit}>
      <div className="booking-form-grid">
        <div className="field-block field-block--span-2">
          <span>Origin</span>
          <SearchSelectField
            options={catalogs.airports.map((item) => ({
              value: item.value,
              label: item.label,
              keywords: `${item.value} ${item.label}`,
              summary: `${item.value} · ${item.label}`,
            }))}
            value={values.originAirport}
            onChange={(value) => update("originAirport", value)}
            placeholder="Search origins"
            allowEmpty
            emptySelectionLabel="Choose"
            disabled={submitting}
          />
        </div>
        <div className="field-block field-block--span-2">
          <span>Destination</span>
          <SearchSelectField
            options={catalogs.airports.map((item) => ({
              value: item.value,
              label: item.label,
              keywords: `${item.value} ${item.label}`,
              summary: `${item.value} · ${item.label}`,
            }))}
            value={values.destinationAirport}
            onChange={(value) => update("destinationAirport", value)}
            placeholder="Search destinations"
            allowEmpty
            emptySelectionLabel="Choose"
            disabled={submitting}
          />
        </div>
        <label className="field-block">
          <span>Departure date</span>
          <input type="date" value={values.departureDate} onChange={(event) => update("departureDate", event.target.value)} disabled={submitting} />
        </label>
        <label className="field-block">
          <span>Departure time</span>
          <input type="time" value={values.departureTime} onChange={(event) => update("departureTime", event.target.value)} disabled={submitting} />
        </label>
        <label className="field-block">
          <span>Arrival time</span>
          <input type="time" value={values.arrivalTime} onChange={(event) => update("arrivalTime", event.target.value)} disabled={submitting} />
        </label>
        <div className="field-block">
          <span>Arrival day</span>
          <SearchSelectField
            options={ARRIVAL_DAY_OPTIONS.map((item) => ({
              value: item.value,
              label: item.label,
              keywords: item.label,
              summary: item.label,
            }))}
            value={values.arrivalDayOffset || "0"}
            onChange={(value) => update("arrivalDayOffset", value)}
            placeholder="Choose day"
            disabled={submitting}
          />
        </div>
        <div className="field-block">
          <span>Airline</span>
          <SearchSelectField
            options={catalogs.airlines.map((item) => ({
              value: item.value,
              label: item.label,
              keywords: `${item.value} ${item.label}`,
              summary: item.label,
            }))}
            value={values.airline}
            onChange={(value) => update("airline", value)}
            placeholder="Search airlines"
            allowEmpty
            emptySelectionLabel="Choose"
            disabled={submitting}
          />
        </div>
        <div className="field-block">
          <span>Fare</span>
          <SearchSelectField
            options={catalogs.fareClasses.map((item) => ({
              value: item.value,
              label: item.label,
              keywords: item.label,
              summary: item.label,
            }))}
            value={values.fareClass}
            onChange={(value) => update("fareClass", value)}
            placeholder="Choose fare"
            disabled={submitting}
          />
        </div>
        <label className="field-block">
          <span>Booked price</span>
          <input type="text" value={values.bookedPrice} onChange={(event) => update("bookedPrice", event.target.value)} disabled={submitting} placeholder="$198" />
        </label>
        <label className="field-block">
          <span>Record locator</span>
          <input type="text" value={values.recordLocator} onChange={(event) => update("recordLocator", event.target.value)} disabled={submitting} placeholder="Optional" />
        </label>
        <label className="field-block field-block--span-2">
          <span>Flight number</span>
          <input type="text" value={values.flightNumber} onChange={(event) => update("flightNumber", event.target.value)} disabled={submitting} placeholder="Optional" />
        </label>
        <label className="field-block field-block--span-2">
          <span>Notes</span>
          <textarea value={values.notes} onChange={(event) => update("notes", event.target.value)} disabled={submitting} rows={2} placeholder="Optional" />
        </label>
      </div>
      {error ? <p className="inline-error">{error}</p> : null}
      <div className="booking-form-actions">
        <button type="button" className="secondary-button" onClick={onCancel} disabled={submitting}>Cancel</button>
        <button type="submit" className="primary-button" disabled={submitting}>{submitting ? busyLabel : submitLabel}</button>
      </div>
    </form>
  );
}
