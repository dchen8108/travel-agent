import { useId, type ReactNode } from "react";

import { CloseIcon } from "./Icons";
import { IconButton } from "./IconButton";

interface Props {
  title: string;
  onClose: () => void;
  children: ReactNode;
}

export function InspectorShell({ title, onClose, children }: Props) {
  const titleId = useId();

  return (
    <aside className="dashboard-inspector" aria-labelledby={titleId}>
      <div className="dashboard-inspector__close-row">
        <h2 className="section-title dashboard-inspector__title" id={titleId}>{title}</h2>
        <IconButton label={`Close ${title.toLowerCase()}`} onClick={onClose}>
          <CloseIcon />
        </IconButton>
      </div>
      <div className="dashboard-inspector__body">
        {children}
      </div>
    </aside>
  );
}
