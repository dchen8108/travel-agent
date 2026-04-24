import { useEffect, useId, useRef, type ReactNode } from "react";

interface Props {
  title: string;
  onClose: () => void;
  headerActions?: ReactNode;
  disableOutsideClose?: boolean;
  children: ReactNode;
}

export function InspectorShell({
  title,
  onClose,
  headerActions = null,
  disableOutsideClose = false,
  children,
}: Props) {
  const titleId = useId();
  const inspectorRef = useRef<HTMLElement | null>(null);

  useEffect(() => {
    if (disableOutsideClose) {
      return;
    }

    function handlePointerDown(event: PointerEvent) {
      const target = event.target as Node;
      if (inspectorRef.current?.contains(target)) {
        return;
      }
      if (target instanceof Element && target.closest("[data-overflow-menu-portal='true']")) {
        return;
      }
      onClose();
    }

    function handleKeyDown(event: KeyboardEvent) {
      if (event.key === "Escape") {
        onClose();
      }
    }

    window.addEventListener("pointerdown", handlePointerDown);
    window.addEventListener("keydown", handleKeyDown);
    return () => {
      window.removeEventListener("pointerdown", handlePointerDown);
      window.removeEventListener("keydown", handleKeyDown);
    };
  }, [disableOutsideClose, onClose]);

  return (
    <aside ref={inspectorRef} className="dashboard-inspector" aria-labelledby={titleId}>
      <div className="dashboard-inspector__close-row">
        <h2 className="section-title dashboard-inspector__title" id={titleId}>{title}</h2>
        {headerActions ? <div className="dashboard-inspector__actions">{headerActions}</div> : null}
      </div>
      <div className="dashboard-inspector__body">
        {children}
      </div>
    </aside>
  );
}
