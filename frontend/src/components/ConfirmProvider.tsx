import { createContext, useCallback, useContext, useMemo, useRef, useState, type ReactNode } from "react";

import { Modal } from "./Modal";

interface ConfirmOptions {
  title: string;
  description?: string;
  actionLabel?: string;
  cancelLabel?: string;
  tone?: "default" | "danger";
}

interface ConfirmRequest extends Required<ConfirmOptions> {
  id: number;
}

interface ConfirmContextValue {
  confirm: (options: ConfirmOptions) => Promise<boolean>;
}

const ConfirmContext = createContext<ConfirmContextValue | null>(null);

export function ConfirmProvider({ children }: { children: ReactNode }) {
  const [request, setRequest] = useState<ConfirmRequest | null>(null);
  const resolverRef = useRef<((value: boolean) => void) | null>(null);
  const nextIdRef = useRef(1);

  const resolveCurrent = useCallback((value: boolean) => {
    resolverRef.current?.(value);
    resolverRef.current = null;
    setRequest(null);
  }, []);

  const confirm = useCallback((options: ConfirmOptions) => {
    return new Promise<boolean>((resolve) => {
      resolverRef.current = resolve;
      setRequest({
        id: nextIdRef.current++,
        title: options.title,
        description: options.description ?? "",
        actionLabel: options.actionLabel ?? "Confirm",
        cancelLabel: options.cancelLabel ?? "Cancel",
        tone: options.tone ?? "default",
      });
    });
  }, []);

  const value = useMemo(() => ({ confirm }), [confirm]);

  return (
    <ConfirmContext.Provider value={value}>
      {children}
      {request ? (
        <Modal title="Confirm" onClose={() => resolveCurrent(false)}>
          <div className="confirm-dialog" key={request.id}>
            <div className="confirm-dialog__copy">
              <strong>{request.title}</strong>
              {request.description ? <p>{request.description}</p> : null}
            </div>
            <div className="confirm-dialog__actions">
              <button type="button" className="secondary-button" onClick={() => resolveCurrent(false)}>
                {request.cancelLabel}
              </button>
              <button
                type="button"
                className={request.tone === "danger" ? "danger-button" : "primary-button"}
                onClick={() => resolveCurrent(true)}
              >
                {request.actionLabel}
              </button>
            </div>
          </div>
        </Modal>
      ) : null}
    </ConfirmContext.Provider>
  );
}

export function useConfirm() {
  const context = useContext(ConfirmContext);
  if (!context) {
    throw new Error("useConfirm must be used inside ConfirmProvider.");
  }
  return context;
}
