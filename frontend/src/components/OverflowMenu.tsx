import { useEffect, useRef, useState, type ReactNode } from "react";

import { MoreIcon } from "./Icons";
import { IconButton } from "./IconButton";
import { PrefetchLink } from "./PrefetchLink";

interface OverflowMenuItem {
  key: string;
  label: string;
  tone?: "default" | "danger";
  icon: ReactNode;
  href?: string;
  onSelect?: () => void;
  onPrefetch?: () => void;
}

interface Props {
  label?: string;
  items: OverflowMenuItem[];
  align?: "start" | "end";
  direction?: "down" | "up";
}

export function OverflowMenu({
  label = "Actions",
  items,
  align = "start",
  direction = "down",
}: Props) {
  const [open, setOpen] = useState(false);
  const menuRef = useRef<HTMLDivElement | null>(null);

  useEffect(() => {
    if (!open) {
      return;
    }

    function handlePointerDown(event: PointerEvent) {
      if (!menuRef.current?.contains(event.target as Node)) {
        setOpen(false);
      }
    }

    function handleKeyDown(event: KeyboardEvent) {
      if (event.key === "Escape") {
        setOpen(false);
      }
    }

    window.addEventListener("pointerdown", handlePointerDown);
    window.addEventListener("keydown", handleKeyDown);
    return () => {
      window.removeEventListener("pointerdown", handlePointerDown);
      window.removeEventListener("keydown", handleKeyDown);
    };
  }, [open]);

  return (
    <div className="overflow-menu" ref={menuRef}>
      <IconButton
        label={label}
        variant="inline"
        className={open ? "overflow-menu__trigger is-open" : "overflow-menu__trigger"}
        aria-haspopup="menu"
        aria-expanded={open}
        onClick={() => setOpen((current) => !current)}
      >
        <MoreIcon />
      </IconButton>
      {open ? (
        <div
          className={`overflow-menu__dropdown${
            align === "end" ? " overflow-menu__dropdown--align-end" : ""
          }${
            direction === "up" ? " overflow-menu__dropdown--direction-up" : ""
          }`}
          role="menu"
          aria-label={label}
        >
          {items.map((item) => (
            item.href ? (
              <PrefetchLink
                key={item.key}
                className={`overflow-menu__item${item.tone === "danger" ? " overflow-menu__item--danger" : ""}`}
                to={item.href}
                role="menuitem"
                onPrefetch={item.onPrefetch}
                onClick={() => setOpen(false)}
              >
                {item.icon}
                <span>{item.label}</span>
              </PrefetchLink>
            ) : (
              <button
                key={item.key}
                type="button"
                className={`overflow-menu__item${item.tone === "danger" ? " overflow-menu__item--danger" : ""}`}
                role="menuitem"
                onMouseEnter={handlePrefetch(item.onPrefetch)}
                onFocus={handlePrefetch(item.onPrefetch)}
                onPointerDown={handlePrefetch(item.onPrefetch)}
                onClick={() => {
                  setOpen(false);
                  item.onSelect?.();
                }}
              >
                {item.icon}
                <span>{item.label}</span>
              </button>
            )
          ))}
        </div>
      ) : null}
    </div>
  );
}

function handlePrefetch(handler?: () => void) {
  return (_event: unknown) => {
    handler?.();
  };
}
