import { useEffect, useState, type KeyboardEvent } from "react";

import { CheckIcon, CloseIcon } from "./Icons";
import { IconButton } from "./IconButton";

interface Props {
  collectionId?: string;
  initialLabel?: string;
  mode: "create" | "edit";
  onCancel: () => void;
  onSave: (label: string) => Promise<unknown>;
}

export function CollectionEditorCard({ collectionId = "", initialLabel = "", mode, onCancel, onSave }: Props) {
  const [label, setLabel] = useState(initialLabel);
  const [error, setError] = useState("");
  const [saving, setSaving] = useState(false);

  useEffect(() => {
    setLabel(initialLabel);
  }, [initialLabel]);

  async function handleSave() {
    setSaving(true);
    setError("");
    try {
      await onSave(label);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Unable to save collection.");
    } finally {
      setSaving(false);
    }
  }

  function handleKeyDown(event: KeyboardEvent<HTMLInputElement>) {
    if (event.key === "Escape") {
      event.preventDefault();
      onCancel();
    }
  }

  return (
    <article className="collection-card collection-card--editing" id={collectionId ? `group-${collectionId}` : undefined}>
      <form
        className="collection-card__editor"
        onSubmit={(event) => {
          event.preventDefault();
          void handleSave();
        }}
      >
        <div className="collection-card__header">
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
            <IconButton label={mode === "create" ? "Create collection" : "Save collection"} onClick={() => void handleSave()} disabled={saving}>
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
