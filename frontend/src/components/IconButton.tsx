import { forwardRef, type ButtonHTMLAttributes, type ReactNode } from "react";

type Props = ButtonHTMLAttributes<HTMLButtonElement> & {
  label: string;
  children: ReactNode;
  tone?: "default" | "danger" | "accent";
  variant?: "default" | "inline";
};

export const IconButton = forwardRef<HTMLButtonElement, Props>(function IconButton(
  { label, children, tone = "default", variant = "default", className = "", ...props },
  ref,
) {
  return (
    <button
      ref={ref}
      type="button"
      aria-label={label}
      title={label}
      className={`icon-button icon-button--${tone} icon-button--${variant} ${className}`.trim()}
      {...props}
    >
      {children}
    </button>
  );
});
