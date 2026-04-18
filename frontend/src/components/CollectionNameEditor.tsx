import { useEffect, useState, type KeyboardEvent } from "react";

import { CheckIcon, CloseIcon } from "./Icons";
import { IconButton } from "./IconButton";

interface Props {
  initialLabel?: string;
  mode: "create" | "edit";
  variant: "card" | "inline";
  onCancel: () => void;
  onSave: (label: string) => Promise<unknown>;
}

export function CollectionNameEditor({
  initialLabel = "",
  mode,
  variant,
  onCancel,
  onSave,
}: Props) {
  const [label, setLabel] = useState(initialLabel);
  const [error, setError] = useState("");
  const [saving, setSaving] = useState(false);

  useEffect(() => {
    setLabel(initialLabel);
    setError("");
    setSaving(false);
  }, [initialLabel, mode, variant]);

  async function handleSave() {
    setSaving(true);
    setError("");
    try {
      await onSave(label);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Unable to save collection.");
      setSaving(false);
    }
  }

  function handleKeyDown(event: KeyboardEvent<HTMLInputElement>) {
    if (event.key === "Escape") {
      event.preventDefault();
      onCancel();
      return;
    }
    if (variant === "inline" && event.key === "Enter") {
      event.preventDefault();
      void handleSave();
    }
  }

  if (variant === "inline") {
    return (
      <>
        <div className="collection-card__titleline">
          <input
            className="collection-card__input collection-card__input--inline"
            value={label}
            onChange={(event) => setLabel(event.target.value)}
            onKeyDown={handleKeyDown}
            placeholder="Collection name"
            disabled={saving}
            autoFocus
          />
          <div className="collection-card__header-actions collection-card__header-actions--inline">
            <IconButton label="Save collection" variant="inline" onClick={() => void handleSave()} disabled={saving} loading={saving}>
              <CheckIcon />
            </IconButton>
            <IconButton label="Cancel" variant="inline" onClick={onCancel} disabled={saving}>
              <CloseIcon />
            </IconButton>
          </div>
        </div>
        {error ? <p className="inline-error">{error}</p> : null}
      </>
    );
  }

  return (
    <article className="collection-card collection-card--editing">
      <form
        className="collection-card__editor"
        onSubmit={(event) => {
          event.preventDefault();
          void handleSave();
        }}
      >
        <div className="collection-card__header collection-card__header--editor">
          <div className="collection-card__titleline collection-card__titleline--editing">
            <span className="collection-card__eyebrow">{mode === "create" ? "New collection" : "Edit collection"}</span>
            <input
              className="collection-card__input"
              value={label}
              onChange={(event) => setLabel(event.target.value)}
              onKeyDown={handleKeyDown}
              placeholder="Collection name"
              disabled={saving}
              autoFocus
            />
          </div>
          <div className="collection-card__header-actions">
            <IconButton
              label={mode === "create" ? "Create collection" : "Save collection"}
              onClick={() => void handleSave()}
              disabled={saving}
              loading={saving}
            >
              <CheckIcon />
            </IconButton>
            <IconButton label="Cancel" onClick={onCancel} disabled={saving}>
              <CloseIcon />
            </IconButton>
          </div>
        </div>
        {error ? <p className="inline-error">{error}</p> : null}
      </form>
    </article>
  );
}
