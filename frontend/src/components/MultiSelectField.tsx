import { useEffect, useId, useMemo, useRef, useState } from "react";

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
  const fieldId = useId();
  const rootRef = useRef<HTMLDivElement>(null);
  const searchRef = useRef<HTMLInputElement>(null);
  const [query, setQuery] = useState("");
  const [open, setOpen] = useState(false);
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
    function handleOpen(event: Event) {
      const detail = (event as CustomEvent<{ fieldId: string }>).detail;
      if (detail?.fieldId !== fieldId) {
        setOpen(false);
      }
    }
    window.addEventListener("multi-select:open", handleOpen as EventListener);
    return () => window.removeEventListener("multi-select:open", handleOpen as EventListener);
  }, [fieldId]);

  useEffect(() => {
    if (!open) {
      return;
    }
    const animation = window.requestAnimationFrame(() => {
      searchRef.current?.focus();
    });

    function handlePointerDown(event: PointerEvent) {
      if (rootRef.current && !rootRef.current.contains(event.target as Node)) {
        setOpen(false);
      }
    }

    function handleKeyDown(event: KeyboardEvent) {
      if (event.key === "Escape") {
        setOpen(false);
      }
    }

    window.addEventListener("pointerdown", handlePointerDown);
    window.addEventListener("keydown", handleKeyDown);
    return () => {
      window.cancelAnimationFrame(animation);
      window.removeEventListener("pointerdown", handlePointerDown);
      window.removeEventListener("keydown", handleKeyDown);
    };
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

  function toggleOpen() {
    setOpen((current) => {
      const next = !current;
      if (next) {
        window.dispatchEvent(new CustomEvent("multi-select:open", { detail: { fieldId } }));
      }
      return next;
    });
  }

  return (
    <div ref={rootRef} className={`multi-select-react${open ? " is-open" : ""}`}>
      <button
        type="button"
        className="multi-select-react__summary"
        aria-expanded={open}
        aria-haspopup="listbox"
        onClick={toggleOpen}
      >
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
      </button>
      {open ? (
        <div className="multi-select-react__panel">
          <input
            ref={searchRef}
            type="text"
            className="multi-select-react__search"
            value={query}
            onChange={(event) => setQuery(event.target.value)}
            placeholder={placeholder}
          />
          <div className="multi-select-react__options" role="listbox" aria-multiselectable="true">
            {filtered.length ? (
              filtered.map((option) => {
                const checked = values.includes(option.value);
                return (
                  <button
                    key={option.value}
                    type="button"
                    className={`multi-select-react__option ${checked ? "is-selected" : ""}`}
                    onClick={() => toggle(option.value)}
                    aria-pressed={checked}
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
      ) : null}
    </div>
  );
}
