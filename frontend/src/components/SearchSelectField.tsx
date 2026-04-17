import { useEffect, useId, useMemo, useState, type ReactNode } from "react";

import { usePickerPopover } from "../lib/usePickerPopover";

interface Option {
  value: string;
  label: string;
  keywords?: string;
  summary?: string;
  meta?: string;
}

interface Props {
  options: Option[];
  value: string;
  onChange: (value: string) => void;
  placeholder: string;
  emptyText?: string;
  allowEmpty?: boolean;
  emptySelectionLabel?: string;
  renderOptionMeta?: (option: Option) => ReactNode;
}

export function SearchSelectField({
  options,
  value,
  onChange,
  placeholder,
  emptyText = "No matches",
  allowEmpty = false,
  emptySelectionLabel = "Choose",
  renderOptionMeta,
}: Props) {
  const { rootRef, searchRef, open, setOpen, toggleOpen } = usePickerPopover();
  const listboxId = useId();
  const [query, setQuery] = useState("");

  const selected = useMemo(
    () => options.find((option) => option.value === value) ?? null,
    [options, value],
  );
  const filtered = useMemo(() => {
    const needle = query.trim().toLowerCase();
    if (!needle) {
      return options;
    }
    return options.filter((option) => {
      const haystack = `${option.value} ${option.label} ${option.keywords ?? ""} ${option.summary ?? ""} ${option.meta ?? ""}`.toLowerCase();
      return haystack.includes(needle);
    });
  }, [options, query]);

  useEffect(() => {
    if (!open) {
      setQuery("");
    }
  }, [open]);

  function selectValue(nextValue: string) {
    onChange(nextValue);
    setOpen(false);
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
        {selected ? (
          <span className="picker-react__single-value">{selected.summary ?? selected.label}</span>
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
          <div className="picker-react__options" id={listboxId} role="listbox" aria-multiselectable="false">
            {filtered.length || (allowEmpty && value) ? (
              <>
                {allowEmpty && value ? (
                  <button
                    type="button"
                    className="picker-react__option"
                    role="option"
                    aria-selected={false}
                    onClick={() => selectValue("")}
                  >
                    <span className="picker-react__option-check" />
                    <span className="picker-react__option-copy">
                      <strong>{emptySelectionLabel}</strong>
                      <small>Clear the current selection</small>
                    </span>
                  </button>
                ) : null}
                {filtered.map((option) => {
                const checked = option.value === value;
                return (
                  <button
                    key={option.value}
                    type="button"
                    className={`picker-react__option ${checked ? "is-selected" : ""}`}
                    onClick={() => selectValue(option.value)}
                    role="option"
                    aria-selected={checked}
                  >
                    <span className="picker-react__option-check">{checked ? "✓" : ""}</span>
                    <span className="picker-react__option-copy">
                      <strong>{option.summary ?? option.value}</strong>
                      {renderOptionMeta ? renderOptionMeta(option) : <small>{option.label}</small>}
                    </span>
                  </button>
                );
                })}
              </>
            ) : (
              <div className="picker-react__empty">{emptyText}</div>
            )}
          </div>
        </div>
      ) : null}
    </div>
  );
}
