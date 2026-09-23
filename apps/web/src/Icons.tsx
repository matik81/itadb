import type { ReactNode } from 'react';

const shapes: Record<string, ReactNode> = {
  persons: (
    <>
      <circle cx="12" cy="6" r="3" />
      <path d="M7 21v-6a5 5 0 0 1 10 0v6M9 15v6m6-6v6" />
    </>
  ),
  households: (
    <>
      <circle cx="6" cy="6" r="2.5" />
      <circle cx="18" cy="6" r="2.5" />
      <circle cx="12" cy="13" r="2" />
      <path d="M2 19v-5a4 4 0 0 1 7-2m13 7v-5a4 4 0 0 0-7-2m-7 9v-2a4 4 0 0 1 8 0v2" />
    </>
  ),
  dwellings: (
    <>
      <path d="m2 11 10-8 10 8M5 9v12h14V9M10 21v-7h4v7" />
    </>
  ),
  country: (
    <>
      <circle cx="12" cy="12" r="9" />
      <ellipse cx="12" cy="12" rx="4" ry="9" />
      <path d="M3 12h18" />
    </>
  ),
  region: (
    <>
      <path d="m3 5 6-2 6 3 6-2v15l-6 2-6-3-6 2ZM9 3v15m6-12v15" />
    </>
  ),
  province: (
    <>
      <path d="m3 5 6-2 6 3 6-2v15l-6 2-6-3-6 2Z" />
      <circle cx="12" cy="11" r="3" />
      <path d="M12 14v4" />
    </>
  ),
  municipality: (
    <>
      <path d="m3 9 9-6 9 6ZM5 9v11m5-11v11m4-11v11m5-11v11M3 21h18" />
    </>
  ),
};
export const levelLabels = {
  country: 'Italia · totale',
  region: 'Regione',
  province: 'Provincia',
  municipality: 'Comune',
};

export function Icon({
  kind,
  label,
  className = '',
}: {
  kind: string;
  label?: string;
  className?: string;
}) {
  if (!shapes[kind]) return null;
  return (
    <svg
      className={`type-icon ${className}`}
      viewBox="0 0 24 24"
      fill="none"
      stroke="currentColor"
      strokeWidth="1.7"
      strokeLinecap="round"
      strokeLinejoin="round"
      role={label ? 'img' : undefined}
      aria-label={label}
      aria-hidden={label ? undefined : true}
    >
      {label && <title>{label}</title>}
      {shapes[kind]}
    </svg>
  );
}
