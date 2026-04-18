const AIRLINE_MARKS: Record<string, { code: string; label: string }> = {
  Alaska: { code: "AS", label: "Alaska Airlines" },
  American: { code: "AA", label: "American Airlines" },
  Delta: { code: "DL", label: "Delta Air Lines" },
  JetBlue: { code: "B6", label: "JetBlue" },
  Southwest: { code: "WN", label: "Southwest Airlines" },
  United: { code: "UA", label: "United Airlines" },
  Hawaiian: { code: "HA", label: "Hawaiian Airlines" },
  Frontier: { code: "F9", label: "Frontier Airlines" },
  Spirit: { code: "NK", label: "Spirit Airlines" },
  "Sun Country": { code: "SY", label: "Sun Country" },
};

function airlineSlug(value: string) {
  return value.toLowerCase().replace(/[^a-z0-9]+/g, "-");
}

export function AirlineMark({ airlineKey }: { airlineKey: string }) {
  const mark = AIRLINE_MARKS[airlineKey];
  if (!mark) {
    return null;
  }

  return (
    <span className={`airline-mark airline-mark--${airlineSlug(airlineKey)}`} aria-hidden="true" title={mark.label}>
      <svg className="airline-mark__shape" viewBox="0 0 32 32" focusable="false" aria-hidden="true">
        <rect x="2" y="2" width="28" height="28" rx="9" fill="var(--airline-mark-bg)" />
        <path d="M2 24.5 14.2 12.3c2.3-2.3 5.4-3.5 8.7-3.5H30V30H11.4c-4.8 0-9.1-2.1-9.4-5.5Z" fill="var(--airline-mark-accent)" opacity="0.92" />
        <path d="M9 21.5 23.5 9" stroke="var(--airline-mark-stripe)" strokeWidth="2.5" strokeLinecap="round" />
      </svg>
      <span className="airline-mark__code">{mark.code}</span>
    </span>
  );
}
