import { useEffect, useLayoutEffect, useRef, useState, type CSSProperties, type ReactNode } from "react";
import { createPortal } from "react-dom";

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
  const [menuStyle, setMenuStyle] = useState<CSSProperties | null>(null);
  const rootRef = useRef<HTMLDivElement | null>(null);
  const triggerRef = useRef<HTMLButtonElement | null>(null);
  const menuRef = useRef<HTMLDivElement | null>(null);

  useEffect(() => {
    if (!open) {
      return;
    }

    function handlePointerDown(event: PointerEvent) {
      const target = event.target as Node;
      if (!menuRef.current?.contains(target) && !rootRef.current?.contains(target)) {
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

  useLayoutEffect(() => {
    if (!open || !triggerRef.current || !menuRef.current) {
      return;
    }

    const gutter = 8;
    const gap = 6;

    const updatePosition = () => {
      if (!triggerRef.current || !menuRef.current) {
        return;
      }
      const triggerRect = triggerRef.current.getBoundingClientRect();
      const menuRect = menuRef.current.getBoundingClientRect();

      let left = align === "end"
        ? triggerRect.right - menuRect.width
        : triggerRect.left;
      left = Math.max(gutter, Math.min(left, window.innerWidth - menuRect.width - gutter));

      let top = direction === "up"
        ? triggerRect.top - menuRect.height - gap
        : triggerRect.bottom + gap;
      top = Math.max(gutter, Math.min(top, window.innerHeight - menuRect.height - gutter));

      setMenuStyle({
        left,
        top,
        visibility: "visible",
      });
    };

    setMenuStyle((current) => ({ ...current, visibility: "hidden" }));
    updatePosition();

    window.addEventListener("resize", updatePosition);
    window.addEventListener("scroll", updatePosition, true);
    return () => {
      window.removeEventListener("resize", updatePosition);
      window.removeEventListener("scroll", updatePosition, true);
    };
  }, [align, direction, open]);

  return (
    <div className="overflow-menu" ref={rootRef}>
      <IconButton
        label={label}
        variant="inline"
        className={open ? "overflow-menu__trigger is-open" : "overflow-menu__trigger"}
        aria-haspopup="menu"
        aria-expanded={open}
        ref={triggerRef}
        onClick={() => setOpen((current) => !current)}
      >
        <MoreIcon />
      </IconButton>
      {open ? createPortal(
        <div
          ref={menuRef}
          className="overflow-menu__dropdown"
          data-overflow-menu-portal="true"
          style={menuStyle ?? { visibility: "hidden" }}
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
        </div>,
        document.body,
      ) : null}
    </div>
  );
}

function handlePrefetch(handler?: () => void) {
  return (_event: unknown) => {
    handler?.();
  };
}
