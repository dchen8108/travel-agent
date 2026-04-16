interface Props {
  options: Array<{ value: string; label: string }>;
  selected: string[];
  includeBooked: boolean;
  onToggleOption: (value: string) => void;
  onToggleBooked: () => void;
}

export function FilterBar({ options, selected, includeBooked, onToggleOption, onToggleBooked }: Props) {
  return (
    <div className="filter-bar">
      <div className="filter-chip-row">
        {options.map((option) => {
          const active = selected.includes(option.value);
          return (
            <button
              key={option.value}
              type="button"
              className={`filter-chip ${active ? "is-active" : ""}`}
              onClick={() => onToggleOption(option.value)}
            >
              {option.label}
            </button>
          );
        })}
      </div>
      <button type="button" className={`filter-toggle ${includeBooked ? "is-active" : ""}`} onClick={onToggleBooked}>
        {includeBooked ? "Showing booked trips" : "Planned trips only"}
      </button>
    </div>
  );
}
