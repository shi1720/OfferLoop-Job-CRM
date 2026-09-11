/** Hero-number tile — the "not a chart" form for single headline values. */

import { cn } from "../../lib/format";

export function StatTile({
  label,
  value,
  sub,
  tone,
}: {
  label: string;
  value: string;
  sub?: string;
  tone?: "good" | "bad";
}) {
  return (
    <div className="ring-card rounded-2xl bg-card p-4">
      <p className="text-[11px] font-medium tracking-wide text-ink-3 uppercase">{label}</p>
      <p
        className={cn(
          "font-display mt-1.5 text-[1.75rem] leading-none font-bold tracking-tight",
          tone === "good" && "text-offer",
          tone === "bad" && "text-reject",
        )}
      >
        {value}
      </p>
      {sub && <p className="mt-1.5 text-xs text-ink-2">{sub}</p>}
    </div>
  );
}
