import { useEffect, useId, useMemo, useState } from "react";

import { usePickerPopover } from "../lib/usePickerPopover";

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
  const { rootRef, searchRef, open, setOpen, toggleOpen } = usePickerPopover();
  const listboxId = useId();
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

  useEffect(() => {
    if (!open) {
      setQuery("");
    }
  }, [open]);

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
    <div ref={rootRef} className={`picker-react${open ? " is-open" : ""}`}>
      <button
        type="button"
        className="picker-react__summary"
        aria-expanded={open}
        aria-haspopup="listbox"
        aria-controls={listboxId}
        onClick={toggleOpen}
      >
        {selected.length ? (
          <span className="picker-react__chips">
            {selected.map((option) => (
              <span key={option.value} className="picker-react__chip">
                {option.value}
              </span>
            ))}
          </span>
        ) : (
          <span className="picker-react__placeholder">{placeholder}</span>
        )}
      </button>
      {open ? (
        <div className="picker-react__panel">
          <input
            ref={searchRef}
            type="text"
            className="picker-react__search"
            value={query}
            onChange={(event) => setQuery(event.target.value)}
            placeholder={placeholder}
          />
          <div className="picker-react__options" id={listboxId} role="listbox" aria-multiselectable="true">
            {filtered.length ? (
              filtered.map((option) => {
                const checked = values.includes(option.value);
                return (
                  <button
                    key={option.value}
                    type="button"
                    className={`picker-react__option ${checked ? "is-selected" : ""}`}
                    onClick={() => toggle(option.value)}
                    role="option"
                    aria-selected={checked}
                  >
                    <span className="picker-react__option-check">{checked ? "✓" : ""}</span>
                    <span className="picker-react__option-copy">
                      <strong>{option.value}</strong>
                      <small>{option.label}</small>
                    </span>
                  </button>
                );
              })
            ) : (
              <div className="picker-react__empty">{emptyText}</div>
            )}
          </div>
        </div>
      ) : null}
    </div>
  );
}
