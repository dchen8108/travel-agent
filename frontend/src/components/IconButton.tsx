import { forwardRef, type ButtonHTMLAttributes, type ReactNode } from "react";

import { RefreshIcon } from "./Icons";

type Props = ButtonHTMLAttributes<HTMLButtonElement> & {
  label: string;
  children: ReactNode;
  tone?: "default" | "danger" | "accent";
  variant?: "default" | "inline";
  loading?: boolean;
};

export const IconButton = forwardRef<HTMLButtonElement, Props>(function IconButton(
  { label, children, tone = "default", variant = "default", className = "", loading = false, disabled, ...props },
  ref,
) {
  return (
    <button
      ref={ref}
      type="button"
      aria-label={label}
      title={label}
      aria-busy={loading}
      className={`icon-button icon-button--${tone} icon-button--${variant} ${className}`.trim()}
      disabled={disabled || loading}
      {...props}
    >
      {loading ? <span className="icon-spin"><RefreshIcon /></span> : children}
    </button>
  );
});
