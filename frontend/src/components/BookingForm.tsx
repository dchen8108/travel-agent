import { useEffect, useState } from "react";

interface Props {
  initialValues: Record<string, string>;
  catalogs: {
    airports: Array<{ value: string; label: string }>;
    airlines: Array<{ value: string; label: string }>;
  };
  submitLabel: string;
  onSubmit: (values: Record<string, string>) => Promise<unknown>;
  onCancel: () => void;
}

export function BookingForm({ initialValues, catalogs, submitLabel, onSubmit, onCancel }: Props) {
  const [values, setValues] = useState<Record<string, string>>(initialValues);
  const [error, setError] = useState("");
  const [submitting, setSubmitting] = useState(false);

  useEffect(() => {
    setValues(initialValues);
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

  return (
    <form className="booking-form-card" onSubmit={handleSubmit}>
      <div className="booking-form-grid">
        <label>
          <span>Airline</span>
          <select value={values.airline} onChange={(event) => update("airline", event.target.value)} disabled={submitting}>
            <option value="">Choose</option>
            {catalogs.airlines.map((item) => (
              <option key={item.value} value={item.value}>{item.label}</option>
            ))}
          </select>
        </label>
        <label>
          <span>Origin</span>
          <select value={values.originAirport} onChange={(event) => update("originAirport", event.target.value)} disabled={submitting}>
            <option value="">Choose</option>
            {catalogs.airports.map((item) => (
              <option key={item.value} value={item.value}>{item.value} · {item.label}</option>
            ))}
          </select>
        </label>
        <label>
          <span>Destination</span>
          <select value={values.destinationAirport} onChange={(event) => update("destinationAirport", event.target.value)} disabled={submitting}>
            <option value="">Choose</option>
            {catalogs.airports.map((item) => (
              <option key={item.value} value={item.value}>{item.value} · {item.label}</option>
            ))}
          </select>
        </label>
        <label>
          <span>Departure date</span>
          <input type="date" value={values.departureDate} onChange={(event) => update("departureDate", event.target.value)} disabled={submitting} />
        </label>
        <label>
          <span>Departure time</span>
          <input type="time" value={values.departureTime} onChange={(event) => update("departureTime", event.target.value)} disabled={submitting} />
        </label>
        <label>
          <span>Arrival time</span>
          <input type="time" value={values.arrivalTime} onChange={(event) => update("arrivalTime", event.target.value)} disabled={submitting} />
        </label>
        <label>
          <span>Booked price</span>
          <input type="text" value={values.bookedPrice} onChange={(event) => update("bookedPrice", event.target.value)} disabled={submitting} placeholder="$198" />
        </label>
        <label>
          <span>Record locator</span>
          <input type="text" value={values.recordLocator} onChange={(event) => update("recordLocator", event.target.value)} disabled={submitting} />
        </label>
      </div>
      <label>
        <span>Notes</span>
        <textarea value={values.notes} onChange={(event) => update("notes", event.target.value)} disabled={submitting} rows={3} />
      </label>
      {error ? <p className="inline-error">{error}</p> : null}
      <div className="booking-form-actions">
        <button type="submit" className="primary-button" disabled={submitting}>{submitLabel}</button>
        <button type="button" className="secondary-button" onClick={onCancel} disabled={submitting}>Cancel</button>
      </div>
    </form>
  );
}
