import type { ReactNode } from "react";

function svg(children: ReactNode) {
  return (
    <svg viewBox="0 0 24 24" aria-hidden="true" focusable="false">
      {children}
    </svg>
  );
}

export function EditIcon() {
  return svg(<path d="M4 20h4l10-10-4-4L4 16v4Zm12.7-12.3 1.6-1.6a1 1 0 0 0 0-1.4l-1.3-1.3a1 1 0 0 0-1.4 0L14 4.9l2.7 2.8Z" fill="currentColor" />);
}

export function DeleteIcon() {
  return svg(
    <>
      <path d="M8 6V4h8v2h4v2H4V6h4Zm1 4h2v8H9v-8Zm4 0h2v8h-2v-8Z" fill="currentColor" />
    </>,
  );
}

export function ViewIcon() {
  return svg(
    <>
      <path d="M12 5c4.6 0 8.3 2.8 10 7-1.7 4.2-5.4 7-10 7S3.7 16.2 2 12c1.7-4.2 5.4-7 10-7Zm0 2c-3.3 0-6.1 1.8-7.7 5 1.6 3.2 4.4 5 7.7 5s6.1-1.8 7.7-5c-1.6-3.2-4.4-5-7.7-5Zm0 2.5A2.5 2.5 0 1 1 12 17a2.5 2.5 0 0 1 0-5Z" fill="currentColor" />
    </>,
  );
}

export function AddIcon() {
  return svg(<path d="M11 5h2v6h6v2h-6v6h-2v-6H5v-2h6V5Z" fill="currentColor" />);
}

export function LinkIcon() {
  return svg(
    <path d="M9.7 14.3a1 1 0 0 1 1.4 0 2 2 0 0 0 2.8 0l3.5-3.5a2 2 0 1 0-2.8-2.8l-1.2 1.2A1 1 0 0 1 12 7.8l1.2-1.2a4 4 0 1 1 5.7 5.7l-3.5 3.5a4 4 0 0 1-5.7 0 1 1 0 0 1 0-1.5ZM14.3 9.7a1 1 0 0 1 0 1.4 2 2 0 0 0 0 2.8 1 1 0 0 1-1.4 1.4 4 4 0 0 1 0-5.7 1 1 0 0 1 1.4 0Zm-4.6 4.6a1 1 0 0 1 0-1.4 2 2 0 0 0 0-2.8L6.2 6.6a2 2 0 0 0-2.8 2.8l1.2 1.2A1 1 0 0 1 3.2 12L2 10.8a4 4 0 0 1 5.7-5.7l3.5 3.5a4 4 0 0 1 0 5.7 1 1 0 0 1-1.5 0Z" fill="currentColor" />
  );
}

export function CheckIcon() {
  return svg(<path d="m9.2 16.6-4.1-4.1 1.4-1.4 2.7 2.7 8.3-8.3 1.4 1.4-9.7 9.7Z" fill="currentColor" />);
}

export function CloseIcon() {
  return svg(<path d="m6.4 5 5.6 5.6L17.6 5 19 6.4 13.4 12 19 17.6 17.6 19 12 13.4 6.4 19 5 17.6 10.6 12 5 6.4 6.4 5Z" fill="currentColor" />);
}

export function RefreshIcon() {
  return svg(
    <path d="M12 5a7 7 0 0 1 6.7 5H16v2h5V7h-2v2A9 9 0 1 0 21 12h-2a7 7 0 1 1-7-7Z" fill="currentColor" />
  );
}

export function DetachIcon() {
  return svg(
    <path d="m9.7 14.3 1.4 1.4-2.7 2.7a4 4 0 1 1-5.7-5.7L5.4 10l1.4 1.4-2.7 2.7a2 2 0 0 0 2.8 2.8l2.8-2.6Zm4.6-4.6-1.4-1.4 2.7-2.7a4 4 0 1 1 5.7 5.7L18.6 14l-1.4-1.4 2.7-2.7a2 2 0 1 0-2.8-2.8l-2.8 2.6ZM8 13.4l5.4-5.4 1.4 1.4-5.4 5.4L8 13.4Z" fill="currentColor" />
  );
}
