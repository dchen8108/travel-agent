interface Props {
  options: Array<{ value: string; label: string }>;
  selected: string[];
  includeBooked: boolean;
  includeSkipped: boolean;
  onToggleOption: (value: string) => void;
  onToggleBooked: () => void;
  onToggleSkipped: () => void;
}

export function FilterBar({
  options,
  selected,
  includeBooked,
  includeSkipped,
  onToggleOption,
  onToggleBooked,
  onToggleSkipped,
}: Props) {
  return (
    <div className="filter-bar" role="group" aria-label="Trip filters">
      <div className="filter-chip-row">
        {options.map((option) => {
          const active = selected.includes(option.value);
          return (
            <button
              key={option.value}
              type="button"
              className={`filter-chip ${active ? "is-active" : ""}`}
              aria-pressed={active}
              onClick={() => onToggleOption(option.value)}
            >
              {option.label}
            </button>
          );
        })}
        {options.length > 0 ? <span className="filter-chip-divider" aria-hidden="true" /> : null}
        <button
          type="button"
          className={`filter-chip ${includeBooked ? "is-active" : ""}`}
          aria-pressed={includeBooked}
          onClick={onToggleBooked}
        >
          Show booked
        </button>
        <button
          type="button"
          className={`filter-chip ${includeSkipped ? "is-active" : ""}`}
          aria-pressed={includeSkipped}
          onClick={onToggleSkipped}
        >
          Show skipped
        </button>
      </div>
    </div>
  );
}
