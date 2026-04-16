import type { ReactNode } from "react";

import { CloseIcon } from "./Icons";
import { IconButton } from "./IconButton";

interface Props {
  title: string;
  onClose: () => void;
  children: ReactNode;
}

export function Modal({ title, onClose, children }: Props) {
  return (
    <div className="modal-backdrop" role="presentation" onClick={onClose}>
      <div className="modal-shell" role="dialog" aria-modal="true" aria-label={title} onClick={(event) => event.stopPropagation()}>
        <div className="modal-close-row">
          <span className="modal-kicker">{title}</span>
          <IconButton label="Close" onClick={onClose}>
            <CloseIcon />
          </IconButton>
        </div>
        {children}
      </div>
    </div>
  );
}
