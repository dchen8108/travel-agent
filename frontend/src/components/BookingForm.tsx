import { useEffect, useState } from "react";

import { SearchSelectField } from "./SearchSelectField";

const ARRIVAL_DAY_OPTIONS = [
  { value: "0", label: "Same day" },
  { value: "1", label: "Next day" },
  { value: "2", label: "2 days later" },
];

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
  const [showDetails, setShowDetails] = useState(false);
  const busyLabel = submitLabel.toLowerCase().includes("create") ? "Creating…" : "Saving…";

  useEffect(() => {
    setValues(initialValues);
    setShowDetails(false);
  }, [initialValues]);

  function update(key: string, value: string) {
    setValues((current) => ({ ...current, [key]: value }));
  }

  async function handleSubmit(event: React.FormEvent<HTMLFormElement>) {
    event.preventDefault();
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

  const hiddenDetailsCount = [
    values.arrivalTime.trim() ? 1 : 0,
    values.arrivalDayOffset && values.arrivalDayOffset !== "0" ? 1 : 0,
    values.fareClass && values.fareClass !== "basic_economy" ? 1 : 0,
    values.flightNumber.trim() ? 1 : 0,
    values.notes.trim() ? 1 : 0,
  ].reduce((total, count) => total + count, 0);

  return (
    <form className="booking-form-card trip-editor-form" onSubmit={handleSubmit}>
      <div className="booking-form-grid">
        <div className="field-block">
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
        <div className="field-block">
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
        <label>
          <span>Departure date</span>
          <input type="date" value={values.departureDate} onChange={(event) => update("departureDate", event.target.value)} disabled={submitting} />
        </label>
        <label>
          <span>Departure time</span>
          <input type="time" value={values.departureTime} onChange={(event) => update("departureTime", event.target.value)} disabled={submitting} />
        </label>
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

        <label>
          <span>Booked price</span>
          <input type="text" value={values.bookedPrice} onChange={(event) => update("bookedPrice", event.target.value)} disabled={submitting} placeholder="$198" />
        </label>
        <label>
          <span>Record locator</span>
          <input type="text" value={values.recordLocator} onChange={(event) => update("recordLocator", event.target.value)} disabled={submitting} placeholder="Optional" />
        </label>
        <div className="booking-form-toggle-row field-block--full">
          <button type="button" className="ghost-button booking-form-toggle" onClick={() => setShowDetails((current) => !current)} disabled={submitting}>
            <span>{showDetails ? "Hide details" : "More details"}</span>
            {!showDetails && hiddenDetailsCount > 0 ? <small>{hiddenDetailsCount} set</small> : null}
          </button>
        </div>

        {showDetails ? (
          <>
            <label>
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
                placeholder="Choose arrival day"
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
            <label>
              <span>Flight number</span>
              <input type="text" value={values.flightNumber} onChange={(event) => update("flightNumber", event.target.value)} disabled={submitting} placeholder="Optional" />
            </label>
            <label className="field-block field-block--full">
              <span>Notes</span>
              <textarea value={values.notes} onChange={(event) => update("notes", event.target.value)} disabled={submitting} rows={2} placeholder="Optional" />
            </label>
          </>
        ) : null}
      </div>
      {error ? <p className="inline-error">{error}</p> : null}
      <div className="booking-form-actions">
        <button type="button" className="secondary-button" onClick={onCancel} disabled={submitting}>Cancel</button>
        <button type="submit" className="primary-button" disabled={submitting}>{submitting ? busyLabel : submitLabel}</button>
      </div>
    </form>
  );
}
