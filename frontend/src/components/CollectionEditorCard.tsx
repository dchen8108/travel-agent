import { useEffect, useState } from "react";
import { CheckIcon, CloseIcon } from "./Icons";
import { IconButton } from "./IconButton";

interface Props {
  initialLabel?: string;
  mode: "create" | "edit";
  onCancel: () => void;
  onSave: (label: string) => Promise<unknown>;
}

export function CollectionEditorCard({ initialLabel = "", mode, onCancel, onSave }: Props) {
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

  return (
    <article className="collection-card collection-card--editing">
      <div className="collection-card__header">
        <input
          className="collection-card__input"
          value={label}
          onChange={(event) => setLabel(event.target.value)}
          placeholder="Collection name"
          disabled={saving}
          autoFocus
        />
        <div className="collection-card__header-actions">
          <IconButton label={mode === "create" ? "Create collection" : "Save collection"} onClick={handleSave} disabled={saving}>
            <CheckIcon />
          </IconButton>
          <IconButton label="Cancel" onClick={onCancel} disabled={saving}>
            <CloseIcon />
          </IconButton>
        </div>
      </div>
      {error ? <p className="inline-error">{error}</p> : null}
    </article>
  );
}
