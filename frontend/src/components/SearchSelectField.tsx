import { useEffect, useId, useMemo, useState, type KeyboardEvent, type ReactNode } from "react";

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
  ariaLabel?: string;
  emptyText?: string;
  allowEmpty?: boolean;
  emptySelectionLabel?: string;
  renderOptionMeta?: (option: Option) => ReactNode;
}

interface RenderedOption {
  key: string;
  value: string;
  option: Option | null;
  clearSelection: boolean;
}

export function SearchSelectField({
  options,
  value,
  onChange,
  placeholder,
  ariaLabel,
  emptyText = "No matches",
  allowEmpty = false,
  emptySelectionLabel = "Choose",
  renderOptionMeta,
}: Props) {
  const { rootRef, summaryRef, searchRef, open, openPicker, closePicker, toggleOpen } = usePickerPopover();
  const listboxId = useId();
  const optionIdPrefix = useId();
  const [query, setQuery] = useState("");
  const [activeIndex, setActiveIndex] = useState(-1);

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
  const renderedOptions = useMemo<RenderedOption[]>(() => {
    const next: RenderedOption[] = filtered.map((option) => ({
      key: option.value,
      value: option.value,
      option,
      clearSelection: false,
    }));
    if (allowEmpty && value) {
      next.unshift({
        key: "__empty__",
        value: "",
        option: null,
        clearSelection: true,
      });
    }
    return next;
  }, [allowEmpty, filtered, value]);

  useEffect(() => {
    if (!open) {
      setQuery("");
      setActiveIndex(-1);
      return;
    }
    const selectedIndex = renderedOptions.findIndex((entry) => entry.value === value);
    setActiveIndex(selectedIndex >= 0 ? selectedIndex : renderedOptions.length > 0 ? 0 : -1);
  }, [open, renderedOptions, value]);

  useEffect(() => {
    if (!open || activeIndex < 0) {
      return;
    }
    const node = rootRef.current?.querySelector<HTMLElement>(`#${optionIdPrefix}-${activeIndex}`);
    node?.scrollIntoView({ block: "nearest" });
  }, [activeIndex, open, optionIdPrefix, rootRef]);

  function selectValue(nextValue: string) {
    onChange(nextValue);
    closePicker();
  }

  function moveActiveIndex(direction: 1 | -1) {
    if (!renderedOptions.length) {
      return;
    }
    setActiveIndex((current) => {
      if (current === -1) {
        return direction === 1 ? 0 : renderedOptions.length - 1;
      }
      return (current + direction + renderedOptions.length) % renderedOptions.length;
    });
  }

  function handleSummaryKeyDown(event: KeyboardEvent<HTMLButtonElement>) {
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
      setActiveIndex(renderedOptions.length > 0 ? 0 : -1);
      return;
    }
    if (event.key === "End") {
      event.preventDefault();
      setActiveIndex(renderedOptions.length > 0 ? renderedOptions.length - 1 : -1);
      return;
    }
    if (event.key === "Enter" && activeIndex >= 0) {
      event.preventDefault();
      selectValue(renderedOptions[activeIndex]!.value);
      return;
    }
    if (event.key === "Escape") {
      event.preventDefault();
      closePicker({ restoreFocus: true });
    }
  }

  return (
    <div ref={rootRef} className={`picker-react${open ? " is-open" : ""}`}>
      <button
        ref={summaryRef}
        type="button"
        className="picker-react__summary"
        aria-label={ariaLabel}
        aria-expanded={open}
        aria-haspopup="listbox"
        aria-controls={listboxId}
        onClick={toggleOpen}
        onKeyDown={handleSummaryKeyDown}
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
            role="combobox"
            aria-expanded={open}
            aria-controls={listboxId}
            aria-activedescendant={activeIndex >= 0 ? `${optionIdPrefix}-${activeIndex}` : undefined}
            aria-autocomplete="list"
            aria-label={ariaLabel ?? placeholder}
            value={query}
            onChange={(event) => setQuery(event.target.value)}
            onKeyDown={handleSearchKeyDown}
            placeholder={placeholder}
          />
          <div className="picker-react__options" id={listboxId} role="listbox" aria-multiselectable="false">
            {renderedOptions.length ? (
              renderedOptions.map((entry, index) => {
                const checked = entry.value === value && !entry.clearSelection;
                return (
                  <button
                    key={entry.key}
                    id={`${optionIdPrefix}-${index}`}
                    type="button"
                    className={`picker-react__option ${checked ? "is-selected" : ""}${index === activeIndex ? " is-active" : ""}`}
                    onClick={() => selectValue(entry.value)}
                    onMouseEnter={() => setActiveIndex(index)}
                    role="option"
                    aria-selected={checked}
                    tabIndex={-1}
                  >
                    {entry.clearSelection ? (
                      <>
                        <span className="picker-react__option-check" />
                        <span className="picker-react__option-copy">
                          <strong>{emptySelectionLabel}</strong>
                          <small>Clear the current selection</small>
                        </span>
                      </>
                    ) : (
                      <>
                        <span className="picker-react__option-check">{checked ? "✓" : ""}</span>
                        <span className="picker-react__option-copy">
                          <strong>{entry.option!.summary ?? entry.option!.value}</strong>
                          {renderOptionMeta ? renderOptionMeta(entry.option!) : <small>{entry.option!.label}</small>}
                        </span>
                      </>
                    )}
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
