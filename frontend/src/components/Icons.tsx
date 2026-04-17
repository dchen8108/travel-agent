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
      <path
        d="M6.5 4.5h11A2.5 2.5 0 0 1 20 7v10a2.5 2.5 0 0 1-2.5 2.5h-11A2.5 2.5 0 0 1 4 17V7a2.5 2.5 0 0 1 2.5-2.5Z"
        fill="none"
        stroke="currentColor"
        strokeLinecap="round"
        strokeLinejoin="round"
        strokeWidth="2"
      />
      <path
        d="M8 9.25h8"
        fill="none"
        stroke="currentColor"
        strokeLinecap="round"
        strokeLinejoin="round"
        strokeWidth="2"
      />
      <path
        d="M8 12.5h6.5"
        fill="none"
        stroke="currentColor"
        strokeLinecap="round"
        strokeLinejoin="round"
        strokeWidth="2"
      />
      <path
        d="M8 15.75h5"
        fill="none"
        stroke="currentColor"
        strokeLinecap="round"
        strokeLinejoin="round"
        strokeWidth="2"
      />
    </>,
  );
}

export function AddIcon() {
  return svg(<path d="M11 5h2v6h6v2h-6v6h-2v-6H5v-2h6V5Z" fill="currentColor" />);
}

export function LinkIcon() {
  return svg(
    <>
      <path
        d="m10 14-2.8 2.8a3 3 0 1 1-4.2-4.2L5.8 9.8a3 3 0 0 1 4.2 0"
        fill="none"
        stroke="currentColor"
        strokeLinecap="round"
        strokeLinejoin="round"
        strokeWidth="2"
      />
      <path
        d="m14 10 2.8-2.8a3 3 0 1 1 4.2 4.2l-2.8 2.8a3 3 0 0 1-4.2 0"
        fill="none"
        stroke="currentColor"
        strokeLinecap="round"
        strokeLinejoin="round"
        strokeWidth="2"
      />
      <path
        d="m9 15 6-6"
        fill="none"
        stroke="currentColor"
        strokeLinecap="round"
        strokeLinejoin="round"
        strokeWidth="2"
      />
    </>
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
    <>
      <path
        d="m8.5 15.5-1.3 1.3a3 3 0 1 1-4.2-4.2l2.1-2.1"
        fill="none"
        stroke="currentColor"
        strokeLinecap="round"
        strokeLinejoin="round"
        strokeWidth="2"
      />
      <path
        d="m15.5 8.5 1.3-1.3a3 3 0 1 1 4.2 4.2l-2.1 2.1"
        fill="none"
        stroke="currentColor"
        strokeLinecap="round"
        strokeLinejoin="round"
        strokeWidth="2"
      />
      <path
        d="m9.5 9.5 5 5"
        fill="none"
        stroke="currentColor"
        strokeLinecap="round"
        strokeLinejoin="round"
        strokeWidth="2"
      />
      <path
        d="M6 18 18 6"
        fill="none"
        stroke="currentColor"
        strokeLinecap="round"
        strokeLinejoin="round"
        strokeWidth="2"
      />
    </>
  );
}
