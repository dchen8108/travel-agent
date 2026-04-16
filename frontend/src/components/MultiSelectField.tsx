import { useMemo, useState } from "react";

interface Option {
  value: string;
  label: string;
  keywords?: string;
}

interface Props {
  options: Option[];
  values: string[];
  onChange: (values: string[]) => void;
  placeholder: string;
  emptyText?: string;
  maxSelections?: number;
}

export function MultiSelectField({
  options,
  values,
  onChange,
  placeholder,
  emptyText = "No selections",
  maxSelections,
}: Props) {
  const [query, setQuery] = useState("");
  const selected = useMemo(
    () => options.filter((option) => values.includes(option.value)),
    [options, values],
  );
  const filtered = useMemo(() => {
    const needle = query.trim().toLowerCase();
    if (!needle) {
      return options;
    }
    return options.filter((option) => {
      const haystack = `${option.value} ${option.label} ${option.keywords ?? ""}`.toLowerCase();
      return haystack.includes(needle);
    });
  }, [options, query]);

  function toggle(value: string) {
    const exists = values.includes(value);
    if (exists) {
      onChange(values.filter((item) => item !== value));
      return;
    }
    if (maxSelections && values.length >= maxSelections) {
      return;
    }
    onChange([...values, value]);
  }

  return (
    <details className="multi-select-react">
      <summary className="multi-select-react__summary">
        {selected.length ? (
          <span className="multi-select-react__chips">
            {selected.map((option) => (
              <span key={option.value} className="multi-select-react__chip">
                {option.value}
              </span>
            ))}
          </span>
        ) : (
          <span className="multi-select-react__placeholder">{placeholder}</span>
        )}
      </summary>
      <div className="multi-select-react__panel">
        <input
          type="text"
          className="multi-select-react__search"
          value={query}
          onChange={(event) => setQuery(event.target.value)}
          placeholder={placeholder}
        />
        <div className="multi-select-react__options">
          {filtered.length ? (
            filtered.map((option) => {
              const checked = values.includes(option.value);
              return (
                <button
                  key={option.value}
                  type="button"
                  className={`multi-select-react__option ${checked ? "is-selected" : ""}`}
                  onClick={() => toggle(option.value)}
                >
                  <span className="multi-select-react__option-check">{checked ? "✓" : ""}</span>
                  <span className="multi-select-react__option-copy">
                    <strong>{option.value}</strong>
                    <small>{option.label}</small>
                  </span>
                </button>
              );
            })
          ) : (
            <div className="multi-select-react__empty">{emptyText}</div>
          )}
        </div>
      </div>
    </details>
  );
}
