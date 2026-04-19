import {
  createContext,
  useCallback,
  useContext,
  useEffect,
  useMemo,
  useRef,
  useState,
  type ReactNode,
} from "react";

import { AlertIcon, CheckIcon, CloseIcon } from "./Icons";
import { IconButton } from "./IconButton";

type ToastKind = "success" | "error";

interface ToastInput {
  message: string;
  kind?: ToastKind;
}

interface ToastRecord extends Required<ToastInput> {
  id: number;
}

interface ToastContextValue {
  pushToast: (input: ToastInput) => void;
}

const ToastContext = createContext<ToastContextValue | null>(null);

function toastToneLabel(kind: ToastKind) {
  return kind === "error" ? "Action failed" : "Saved";
}

export function ToastProvider({ children }: { children: ReactNode }) {
  const [toasts, setToasts] = useState<ToastRecord[]>([]);
  const nextIdRef = useRef(1);

  const removeToast = useCallback((toastId: number) => {
    setToasts((current) => current.filter((toast) => toast.id !== toastId));
  }, []);

  const pushToast = useCallback(({ message, kind = "success" }: ToastInput) => {
    if (!message.trim()) {
      return;
    }
    const toastId = nextIdRef.current++;
    setToasts((current) => [...current, { id: toastId, message, kind }]);
  }, []);

  useEffect(() => {
    if (!toasts.length) {
      return;
    }
    const timers = toasts.map((toast) => (
      window.setTimeout(() => removeToast(toast.id), toast.kind === "error" ? 6000 : 4200)
    ));
    return () => {
      timers.forEach((timerId) => window.clearTimeout(timerId));
    };
  }, [removeToast, toasts]);

  const value = useMemo(() => ({ pushToast }), [pushToast]);

  return (
    <ToastContext.Provider value={value}>
      {children}
      <div className="toast-viewport" aria-live="polite" aria-atomic="true">
        {toasts.map((toast) => (
          <div key={toast.id} className={`toast toast--${toast.kind}`} role={toast.kind === "error" ? "alert" : "status"}>
            <div className={`toast__icon toast__icon--${toast.kind}`} aria-hidden="true">
              {toast.kind === "error" ? <AlertIcon /> : <CheckIcon />}
            </div>
            <div className="toast__content">
              <strong>{toastToneLabel(toast.kind)}</strong>
              <span>{toast.message}</span>
            </div>
            <IconButton label="Dismiss notification" variant="inline" className="toast__dismiss" onClick={() => removeToast(toast.id)}>
              <CloseIcon />
            </IconButton>
          </div>
        ))}
      </div>
    </ToastContext.Provider>
  );
}

export function useToast() {
  const context = useContext(ToastContext);
  if (!context) {
    throw new Error("useToast must be used inside ToastProvider.");
  }
  return context;
}
