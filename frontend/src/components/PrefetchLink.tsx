import type { FocusEventHandler, MouseEventHandler, PointerEventHandler, ReactNode } from "react";
import { Link, type LinkProps } from "react-router-dom";

interface Props extends LinkProps {
  children: ReactNode;
  onPrefetch?: () => void;
}

export function PrefetchLink({
  children,
  onPrefetch,
  onMouseEnter,
  onFocus,
  onPointerDown,
  ...props
}: Props) {
  const handleMouseEnter: MouseEventHandler<HTMLAnchorElement> = (event) => {
    onMouseEnter?.(event);
    onPrefetch?.();
  };
  const handleFocus: FocusEventHandler<HTMLAnchorElement> = (event) => {
    onFocus?.(event);
    onPrefetch?.();
  };
  const handlePointerDown: PointerEventHandler<HTMLAnchorElement> = (event) => {
    onPointerDown?.(event);
    onPrefetch?.();
  };

  return (
    <Link
      {...props}
      onMouseEnter={handleMouseEnter}
      onFocus={handleFocus}
      onPointerDown={handlePointerDown}
    >
      {children}
    </Link>
  );
}
