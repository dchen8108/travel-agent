import { useState } from "react";

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

export function AirlineMark({ airlineKey }: { airlineKey: string }) {
  const mark = AIRLINE_MARKS[airlineKey];
  const [logoFailed, setLogoFailed] = useState(false);
  if (!mark) {
    return null;
  }

  if (!logoFailed) {
    const src = `https://www.gstatic.com/flights/airline_logos/70px/${mark.code}.png`;
    return (
      <span className="airline-mark airline-mark--logo" aria-hidden="true" title={mark.label}>
        <img className="airline-mark__image" src={src} alt="" loading="lazy" onError={() => setLogoFailed(true)} />
      </span>
    );
  }

  return (
    <span className="airline-mark airline-mark--fallback" aria-hidden="true" title={mark.label}>
      <span className="airline-mark__code">{mark.code}</span>
    </span>
  );
}
