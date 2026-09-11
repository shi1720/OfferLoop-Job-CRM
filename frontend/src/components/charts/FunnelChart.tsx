/** Pipeline funnel — ordinal single-hue ramp (validated against the card
 * surface), thin horizontal bars with rounded data-ends, direct labels,
 * and a per-mark hover tooltip. */

import { useState } from "react";

// Ordinal blue ramp, light→dark down the funnel (validator: PASS on #151a25)
const RAMP = ["#86b6ef", "#3987e5", "#1c5cab"];

interface Stage {
  label: string;
  value: number;
}

export function FunnelChart({ total, interview, offer }: { total: number; interview: number; offer: number }) {
  const stages: Stage[] = [
    { label: "Applications", value: total },
    { label: "Reached interview", value: interview },
    { label: "Reached offer", value: offer },
  ];
  const max = Math.max(total, 1);
  const [hover, setHover] = useState<number | null>(null);

  return (
    <div role="img" aria-label={`Funnel: ${total} applications, ${interview} interviews, ${offer} offers`}>
      <div className="space-y-3">
        {stages.map((stage, index) => {
          const width = Math.max((stage.value / max) * 100, stage.value > 0 ? 3 : 0);
          const conversion =
            index === 0 || stages[index - 1]!.value === 0
              ? null
              : Math.round((stage.value / stages[index - 1]!.value) * 100);
          return (
            <div
              key={stage.label}
              onMouseEnter={() => setHover(index)}
              onMouseLeave={() => setHover(null)}
              className="cursor-default"
            >
              <div className="mb-1 flex items-baseline justify-between text-xs">
                <span className="font-medium text-ink-2">{stage.label}</span>
                <span className="text-ink">
                  <span className="font-display font-bold">{stage.value}</span>
                  {conversion !== null && (
                    <span className={hover === index ? "text-ink-2" : "text-ink-3"}> · {conversion}% convert</span>
                  )}
                </span>
              </div>
              <div className="h-4 w-full rounded-[4px] bg-raised/60">
                <div
                  className="h-4 rounded-[4px] transition-all duration-300"
                  style={{
                    width: `${width}%`,
                    background: RAMP[index],
                    opacity: hover === null || hover === index ? 1 : 0.45,
                  }}
                />
              </div>
            </div>
          );
        })}
      </div>
    </div>
  );
}
