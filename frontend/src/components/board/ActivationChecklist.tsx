/** "First moves" activation checklist: the four actions that make OfferLoop
 * click, each with its momentum reward. Computed from real data (no fake
 * progress), hidden once complete or dismissed. */

import { useQuery } from "@tanstack/react-query";
import { Check, X } from "lucide-react";
import { useState } from "react";

import { api } from "../../api";
import { cn } from "../../lib/format";
import type { Application, Draft } from "../../types";

const DISMISS_KEY = "offerloop:first-moves-dismissed";

export function ActivationChecklist({
  apps,
  drafts,
  onLog,
  onOpenFirst,
  onScan,
}: {
  apps: Application[] | undefined;
  drafts: Draft[] | undefined;
  onLog: () => void;
  onOpenFirst: (() => void) | null;
  onScan: () => void;
}) {
  const [dismissed, setDismissed] = useState(() => {
    try {
      return localStorage.getItem(DISMISS_KEY) === "1";
    } catch {
      return false;
    }
  });
  const { data: nudges } = useQuery({ queryKey: ["nudges", "all"], queryFn: () => api.nudges.list() });

  if (dismissed || !apps || !drafts || !nudges) return null;

  const items = [
    { label: "Log or import an application", reward: "+10", done: apps.length > 0, action: onLog },
    {
      label: "Generate an AI draft",
      reward: "grounded in your voice",
      done: drafts.length > 0,
      action: onOpenFirst ?? onLog, // no applications yet → guide there first
    },
    {
      label: "Send your first outreach",
      reward: "+15",
      done: drafts.some((d) => d.status === "sent"),
      action: onOpenFirst ?? onLog,
    },
    { label: "Scan your pipeline", reward: "auto-drafted nudges", done: nudges.length > 0, action: onScan },
  ];
  const doneCount = items.filter((item) => item.done).length;
  if (doneCount === items.length) return null;

  const dismiss = () => {
    setDismissed(true);
    try {
      localStorage.setItem(DISMISS_KEY, "1");
    } catch {
      /* private mode */
    }
  };

  return (
    <div className="animate-rise mx-6 mb-4 rounded-xl border border-accent/20 bg-accent/5 px-4 py-3">
      <div className="flex items-center justify-between">
        <p className="text-[13px] font-semibold text-ink">
          First moves <span className="ml-1 font-normal text-ink-3">{doneCount}/{items.length}</span>
        </p>
        <button
          onClick={dismiss}
          aria-label="Dismiss checklist"
          className="cursor-pointer rounded-md p-1 text-ink-3 transition-colors hover:bg-raised hover:text-ink"
        >
          <X size={13} />
        </button>
      </div>
      <div className="mt-2 flex flex-wrap gap-2">
        {items.map((item) => (
          <button
            key={item.label}
            onClick={() => !item.done && item.action()}
            disabled={item.done}
            className={cn(
              "flex items-center gap-1.5 rounded-full border px-3 py-1.5 text-xs transition-all",
              item.done
                ? "border-offer/30 bg-offer/5 text-ink-3 line-through"
                : "cursor-pointer border-line text-ink-2 hover:border-accent/50 hover:text-ink",
            )}
          >
            <span
              className={cn(
                "flex h-3.5 w-3.5 items-center justify-center rounded-full border",
                item.done ? "border-offer bg-offer text-page" : "border-ink-3",
              )}
            >
              {item.done && <Check size={9} strokeWidth={3.5} />}
            </span>
            {item.label}
            <span className={cn("font-medium", item.done ? "text-ink-3" : "text-accent")}>{item.reward}</span>
          </button>
        ))}
      </div>
    </div>
  );
}
