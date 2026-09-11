/** The OfferLoop mark: an open loop closing on its target. */

export function LogoMark({ size = 28 }: { size?: number }) {
  return (
    <svg width={size} height={size} viewBox="0 0 32 32" fill="none" aria-hidden>
      <rect width="32" height="32" rx="8" fill="var(--color-page)" />
      <path
        d="M16 7a9 9 0 1 1-8.6 6.3"
        stroke="var(--color-accent)"
        strokeWidth="3.2"
        strokeLinecap="round"
      />
      <circle cx="16" cy="16" r="3.2" fill="var(--color-accent)" />
    </svg>
  );
}

export function Wordmark({ compact = false }: { compact?: boolean }) {
  return (
    <span className="flex items-center gap-2.5">
      <LogoMark />
      {!compact && (
        <span className="font-display text-[17px] font-bold tracking-tight text-ink">
          Offer<span className="text-accent">Loop</span>
        </span>
      )}
    </span>
  );
}
