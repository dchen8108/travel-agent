import { forwardRef, type ButtonHTMLAttributes, type ReactNode } from "react";

type Props = ButtonHTMLAttributes<HTMLButtonElement> & {
  label: string;
  children: ReactNode;
  tone?: "default" | "danger" | "accent";
};

export const IconButton = forwardRef<HTMLButtonElement, Props>(function IconButton(
  { label, children, tone = "default", className = "", ...props },
  ref,
) {
  return (
    <button
      ref={ref}
      type="button"
      aria-label={label}
      title={label}
      className={`icon-button icon-button--${tone} ${className}`.trim()}
      {...props}
    >
      {children}
    </button>
  );
});
