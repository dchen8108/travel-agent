import { useEffect, useId, useRef, useState } from "react";

const PICKER_OPEN_EVENT = "picker:open";

export function usePickerPopover() {
  const fieldId = useId();
  const rootRef = useRef<HTMLDivElement>(null);
  const summaryRef = useRef<HTMLButtonElement>(null);
  const searchRef = useRef<HTMLInputElement>(null);
  const [open, setOpen] = useState(false);

  useEffect(() => {
    function handleOpen(event: Event) {
      const detail = (event as CustomEvent<{ fieldId: string }>).detail;
      if (detail?.fieldId !== fieldId) {
        setOpen(false);
      }
    }

    window.addEventListener(PICKER_OPEN_EVENT, handleOpen as EventListener);
    return () => window.removeEventListener(PICKER_OPEN_EVENT, handleOpen as EventListener);
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
        closePicker();
      }
    }

    function handleKeyDown(event: KeyboardEvent) {
      if (event.key === "Escape") {
        closePicker({ restoreFocus: true });
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

  function openPicker() {
    window.dispatchEvent(new CustomEvent(PICKER_OPEN_EVENT, { detail: { fieldId } }));
    setOpen(true);
  }

  function closePicker({ restoreFocus = false }: { restoreFocus?: boolean } = {}) {
    setOpen(false);
    if (restoreFocus) {
      window.requestAnimationFrame(() => {
        summaryRef.current?.focus();
      });
    }
  }

  function toggleOpen() {
    setOpen((current) => {
      const next = !current;
      if (next) {
        window.dispatchEvent(new CustomEvent(PICKER_OPEN_EVENT, { detail: { fieldId } }));
      }
      return next;
    });
  }

  return {
    rootRef,
    summaryRef,
    searchRef,
    open,
    setOpen,
    openPicker,
    closePicker,
    toggleOpen,
  };
}
