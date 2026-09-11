/** Weekly activity — stacked bars, three validated categorical series,
 * 2px surface gaps between segments, legend + per-bar hover tooltip. */

import { useState } from "react";

import { shortDate } from "../../lib/format";
import type { WeekActivity } from "../../types";

const SERIES = [
  { key: "applications", label: "Applications", color: "var(--color-series-1)" },
  { key: "drafts", label: "Drafts", color: "var(--color-series-2)" },
  { key: "status_changes", label: "Stage moves", color: "var(--color-series-3)" },
] as const;

const HEIGHT = 150;

export function WeeklyActivity({ weeks }: { weeks: WeekActivity[] }) {
  const [hover, setHover] = useState<number | null>(null);
  const max = Math.max(...weeks.map((w) => w.applications + w.drafts + w.status_changes), 1);

  return (
    <div>
      {/* Legend — identity never rides on color alone; labels sit beside marks */}
      <div className="mb-3 flex flex-wrap items-center gap-4">
        {SERIES.map((series) => (
          <span key={series.key} className="inline-flex items-center gap-1.5 text-xs text-ink-2">
            <span className="h-2.5 w-2.5 rounded-[3px]" style={{ background: series.color }} />
            {series.label}
          </span>
        ))}
      </div>

      <div className="relative">
        <div className="flex h-[150px] items-end gap-2">
          {weeks.map((week, index) => {
            const total = week.applications + week.drafts + week.status_changes;
            return (
              <div
                key={week.week_start}
                className="group relative flex h-full flex-1 cursor-default flex-col items-stretch justify-end"
                onMouseEnter={() => setHover(index)}
                onMouseLeave={() => setHover(null)}
              >
                {/* stacked segments, top-down render order = reverse stack */}
                {[...SERIES].reverse().map((series) => {
                  const value = week[series.key];
                  if (value === 0) return null;
                  const height = Math.max((value / max) * (HEIGHT - 8), 3);
                  return (
                    <div
                      key={series.key}
                      className="w-full rounded-[3px] transition-opacity"
                      style={{
                        height,
                        background: series.color,
                        marginTop: 2, // 2px surface gap between stacked segments
                        opacity: hover === null || hover === index ? 1 : 0.4,
                      }}
                    />
                  );
                })}
                {total === 0 && <div className="h-[3px] w-full rounded-[3px] bg-raised" />}

                {/* tooltip */}
                {hover === index && total > 0 && (
                  <div className="ring-card pointer-events-none absolute bottom-full left-1/2 z-10 mb-2 w-40 -translate-x-1/2 rounded-lg bg-overlay p-2.5 text-[11px]">
                    <p className="mb-1 font-semibold text-ink">Week of {shortDate(week.week_start)}</p>
                    {SERIES.map((series) => (
                      <p key={series.key} className="flex items-center gap-1.5 text-ink-2">
                        <span className="h-2 w-2 rounded-[2px]" style={{ background: series.color }} />
                        {series.label}
                        <span className="ml-auto font-medium text-ink">{week[series.key]}</span>
                      </p>
                    ))}
                  </div>
                )}
              </div>
            );
          })}
        </div>

        {/* x labels */}
        <div className="mt-1.5 flex gap-2 border-t border-line-soft pt-1.5">
          {weeks.map((week) => (
            <span key={week.week_start} className="flex-1 text-center text-[10px] text-ink-3">
              {shortDate(week.week_start)}
            </span>
          ))}
        </div>
      </div>
    </div>
  );
}
