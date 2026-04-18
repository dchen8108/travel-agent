import { useEffect, useId, useMemo, useState, type KeyboardEvent } from "react";

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
  disabled?: boolean;
  emptyText?: string;
  maxSelections?: number;
}

export function MultiSelectField({
  options,
  values,
  onChange,
  placeholder,
  disabled = false,
  emptyText = "No selections",
  maxSelections,
}: Props) {
  const { rootRef, summaryRef, searchRef, open, openPicker, closePicker, toggleOpen } = usePickerPopover();
  const listboxId = useId();
  const optionIdPrefix = useId();
  const [query, setQuery] = useState("");
  const [activeIndex, setActiveIndex] = useState(-1);
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
      const haystack = `${option.label} ${option.keywords ?? ""}`.toLowerCase();
      return haystack.includes(needle);
    });
  }, [options, query]);

  useEffect(() => {
    if (disabled) {
      closePicker();
    }
  }, [closePicker, disabled]);

  useEffect(() => {
    if (!open) {
      setQuery("");
      setActiveIndex(-1);
      return;
    }
    const selectedIndex = filtered.findIndex((option) => values.includes(option.value));
    setActiveIndex(selectedIndex >= 0 ? selectedIndex : filtered.length > 0 ? 0 : -1);
  }, [filtered, open, values]);

  useEffect(() => {
    if (!open || activeIndex < 0) {
      return;
    }
    const node = rootRef.current?.querySelector<HTMLElement>(`#${optionIdPrefix}-${activeIndex}`);
    node?.scrollIntoView({ block: "nearest" });
  }, [activeIndex, open, optionIdPrefix, rootRef]);

  function toggle(value: string) {
    const exists = values.includes(value);
    if (disabled) {
      return;
    }
    if (exists) {
      onChange(values.filter((item) => item !== value));
      return;
    }
    if (maxSelections && values.length >= maxSelections) {
      return;
    }
    onChange([...values, value]);
  }

  function moveActiveIndex(direction: 1 | -1) {
    if (!filtered.length) {
      return;
    }
    setActiveIndex((current) => {
      if (current === -1) {
        return direction === 1 ? 0 : filtered.length - 1;
      }
      return (current + direction + filtered.length) % filtered.length;
    });
  }

  function handleSummaryKeyDown(event: KeyboardEvent<HTMLButtonElement>) {
    if (disabled) {
      return;
    }
    if (event.key === "ArrowDown" || event.key === "ArrowUp" || event.key === "Enter" || event.key === " ") {
      event.preventDefault();
      openPicker();
    }
  }

  function handleSearchKeyDown(event: KeyboardEvent<HTMLInputElement>) {
    if (event.key === "ArrowDown") {
      event.preventDefault();
      moveActiveIndex(1);
      return;
    }
    if (event.key === "ArrowUp") {
      event.preventDefault();
      moveActiveIndex(-1);
      return;
    }
    if (event.key === "Home") {
      event.preventDefault();
      setActiveIndex(filtered.length > 0 ? 0 : -1);
      return;
    }
    if (event.key === "End") {
      event.preventDefault();
      setActiveIndex(filtered.length > 0 ? filtered.length - 1 : -1);
      return;
    }
    if ((event.key === "Enter" || event.key === " ") && activeIndex >= 0) {
      event.preventDefault();
      toggle(filtered[activeIndex]!.value);
      return;
    }
    if (event.key === "Escape") {
      event.preventDefault();
      closePicker({ restoreFocus: true });
    }
  }

  return (
    <div ref={rootRef} className={`picker-react${open ? " is-open" : ""}${disabled ? " is-disabled" : ""}`}>
      <button
        ref={summaryRef}
        type="button"
        className="picker-react__summary"
        aria-expanded={open}
        aria-haspopup="listbox"
        aria-controls={listboxId}
        disabled={disabled}
        onClick={toggleOpen}
        onKeyDown={handleSummaryKeyDown}
      >
        {selected.length ? (
          <span className="picker-react__chips">
            {selected.map((option) => (
              <span key={option.value} className="picker-react__chip">
                {option.label}
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
            role="combobox"
            aria-expanded={open}
            aria-controls={listboxId}
            aria-activedescendant={activeIndex >= 0 ? `${optionIdPrefix}-${activeIndex}` : undefined}
            aria-autocomplete="list"
            disabled={disabled}
            value={query}
            onChange={(event) => setQuery(event.target.value)}
            onKeyDown={handleSearchKeyDown}
            placeholder={placeholder}
          />
          <div className="picker-react__options" id={listboxId} role="listbox" aria-multiselectable="true">
            {filtered.length ? (
              filtered.map((option, index) => {
                const checked = values.includes(option.value);
                return (
                  <button
                    key={option.value}
                    id={`${optionIdPrefix}-${index}`}
                    type="button"
                    className={`picker-react__option ${checked ? "is-selected" : ""}${index === activeIndex ? " is-active" : ""}`}
                    onClick={() => toggle(option.value)}
                    onMouseEnter={() => setActiveIndex(index)}
                    role="option"
                    aria-selected={checked}
                    tabIndex={-1}
                  >
                    <span className="picker-react__option-check">{checked ? "✓" : ""}</span>
                    <span className="picker-react__option-copy">
                      <strong>{option.label}</strong>
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
