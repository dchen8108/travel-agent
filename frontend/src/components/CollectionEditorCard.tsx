import { CollectionNameEditor } from "./CollectionNameEditor";

interface Props {
  collectionId?: string;
  initialLabel?: string;
  mode: "create" | "edit";
  onCancel: () => void;
  onSave: (label: string) => Promise<unknown>;
}

export function CollectionEditorCard({ collectionId = "", initialLabel = "", mode, onCancel, onSave }: Props) {
  return (
    <div id={collectionId ? `group-${collectionId}` : undefined}>
      <CollectionNameEditor
        mode={mode}
        variant="card"
        initialLabel={initialLabel}
        onCancel={onCancel}
        onSave={onSave}
      />
    </div>
  );
}
