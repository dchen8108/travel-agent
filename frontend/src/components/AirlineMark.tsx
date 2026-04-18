import alaskaLogo from "../assets/airlines/AS.png";

const AIRLINE_MARKS: Record<string, { code: string; label: string; src?: string }> = {
  Alaska: { code: "AS", label: "Alaska Airlines", src: alaskaLogo },
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
  if (!mark) {
    return null;
  }

  if (mark.src) {
    return (
      <span className="airline-mark airline-mark--logo" aria-hidden="true" title={mark.label}>
        <img className="airline-mark__image" src={mark.src} alt="" />
      </span>
    );
  }

  return (
    <span className="airline-mark airline-mark--fallback" aria-hidden="true" title={mark.label}>
      <span className="airline-mark__code">{mark.code}</span>
    </span>
  );
}
