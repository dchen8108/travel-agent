interface Props {
  options: Array<{ value: string; label: string }>;
  selected: string[];
  includeBooked: boolean;
  onToggleOption: (value: string) => void;
  onToggleBooked: () => void;
}

export function FilterBar({ options, selected, includeBooked, onToggleOption, onToggleBooked }: Props) {
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
      </div>
    </div>
  );
}
