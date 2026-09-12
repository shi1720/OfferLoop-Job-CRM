import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import {
  BadgeCheck,
  BellRing,
  CalendarPlus,
  Check,
  ChevronDown,
  Ghost,
  Mail,
  MessageSquareQuote,
  RadarIcon,
  Sparkles,
  X,
} from "lucide-react";
import { useState } from "react";
import { Link } from "react-router-dom";

import { api } from "../api";
import { useAuth } from "../auth";
import { calendarEventUrl } from "../lib/links";
import { useToast } from "../components/Toast";
import { Button, Chip, EmptyState, Spinner } from "../components/ui";
import { cn, daysSince, timeAgo } from "../lib/format";
import type { Nudge } from "../types";

const RULE_META = {
  follow_up: { icon: Mail, label: "Follow-up due", color: "text-applied" },
  interview_thank_you: { icon: Sparkles, label: "Thank-you note", color: "text-interview" },
  offer_response: { icon: BadgeCheck, label: "Offer response", color: "text-offer" },
  reject_feedback: { icon: MessageSquareQuote, label: "Feedback request", color: "text-reject" },
} as const;

export default function NudgesPage() {
  const queryClient = useQueryClient();
  const toast = useToast();
  const { config } = useAuth();
  const [showHistory, setShowHistory] = useState(false);

  const { data: nudges, isLoading } = useQuery({
    queryKey: ["nudges", "all"],
    queryFn: () => api.nudges.list(),
    // Cloud Scheduler creates nudges server-side — poll so the inbox
    // updates without a manual refresh (same cadence as the sidebar badge).
    refetchInterval: 60_000,
    refetchOnWindowFocus: true,
  });

  const invalidate = () => void queryClient.invalidateQueries({ queryKey: ["nudges"] });

  const scan = useMutation({
    mutationFn: api.scan,
    onSuccess: (report) => {
      toast(
        report.nudges_created > 0
          ? `${report.nudges_created} new nudge${report.nudges_created > 1 ? "s" : ""} — ${report.drafts_generated} follow-up${report.drafts_generated === 1 ? "" : "s"} drafted for you`
          : "Pipeline scanned — you're on top of everything",
        "info",
      );
      invalidate();
      void queryClient.invalidateQueries({ queryKey: ["drafts"] });
    },
  });

  const act = useMutation({
    mutationFn: ({ id, action }: { id: string; action: "done" | "dismiss" }) =>
      action === "done" ? api.nudges.done(id) : api.nudges.dismiss(id),
    onSuccess: (_, { action }) => {
      toast(action === "done" ? "Done — +20 momentum" : "Dismissed", action === "done" ? "ok" : "info");
      invalidate();
      if (action === "done") void queryClient.invalidateQueries({ queryKey: ["profile"] });
    },
  });

  const pending = (nudges ?? []).filter((n) => n.status === "pending");
  const resolved = (nudges ?? []).filter((n) => n.status !== "pending");
  const backoff = config?.cadence.follow_up_backoff_days ?? [];

  return (
    <div className="animate-rise mx-auto max-w-3xl px-4 py-6 sm:px-6">
      <header className="mb-5 flex items-start justify-between gap-4">
        <div>
          <h1 className="font-display text-xl font-bold tracking-tight">Nudges</h1>
          <p className="text-[13px] text-ink-2">
            Cloud Scheduler scans your pipeline every hour. This is what it found.
          </p>
        </div>
        <Button variant="primary" onClick={() => scan.mutate()} disabled={scan.isPending}>
          {scan.isPending ? <Spinner className="border-on-accent/30 border-t-on-accent" /> : <RadarIcon size={15} />}
          Scan now
        </Button>
      </header>

      <div className="mb-5 flex flex-wrap items-center gap-2">
        <span className="text-[11px] font-medium tracking-wide text-ink-3 uppercase">Cadence</span>
        {backoff.map((days, index) => (
          <Chip key={index}>
            touch {index + 1} · {days}d quiet
          </Chip>
        ))}
        <Chip>thank-you · {config?.cadence.interview_thank_you_days ?? 1}d after interview</Chip>
        <Chip>offer reply · {config?.cadence.offer_response_days ?? 3}d</Chip>
      </div>

      {isLoading ? (
        <div className="flex justify-center py-16">
          <Spinner />
        </div>
      ) : pending.length === 0 ? (
        <EmptyState
          icon={<BellRing size={28} />}
          title="Inbox zero — pipeline fully worked"
          hint="Every application has been touched on schedule. New nudges appear here the moment something goes quiet."
          action={
            <Button variant="outline" onClick={() => scan.mutate()}>
              <RadarIcon size={14} /> Run a scan anyway
            </Button>
          }
        />
      ) : (
        <ul className="space-y-3">
          {pending.map((nudge) => (
            <NudgeCard key={nudge.id} nudge={nudge} onAct={(action) => act.mutate({ id: nudge.id, action })} />
          ))}
        </ul>
      )}

      {resolved.length > 0 && (
        <div className="mt-8">
          <button
            onClick={() => setShowHistory((current) => !current)}
            className="flex cursor-pointer items-center gap-1.5 text-xs font-medium text-ink-3 hover:text-ink-2"
          >
            <ChevronDown size={13} className={cn("transition-transform", showHistory && "rotate-180")} />
            History ({resolved.length})
          </button>
          {showHistory && (
            <ul className="mt-3 space-y-2 opacity-60">
              {resolved.map((nudge) => (
                <li key={nudge.id} className="flex items-center gap-2 rounded-lg border border-line-soft px-3 py-2 text-sm">
                  <span className={cn("text-xs", nudge.status === "done" ? "text-offer" : "text-ink-3")}>
                    {nudge.status === "done" ? <Check size={13} /> : <X size={13} />}
                  </span>
                  <span className="flex-1 truncate text-ink-2">{nudge.headline}</span>
                  <span className="text-[11px] text-ink-3">{timeAgo(nudge.created_at)}</span>
                </li>
              ))}
            </ul>
          )}
        </div>
      )}
    </div>
  );
}

function NudgeCard({ nudge, onAct }: { nudge: Nudge; onAct: (action: "done" | "dismiss") => void }) {
  const meta = RULE_META[nudge.rule];
  const Icon = meta?.icon ?? BellRing;
  const overdue = daysSince(nudge.due_at);

  const { data: draft } = useQuery({
    queryKey: ["draft-preview", nudge.draft_id],
    queryFn: async () => {
      const drafts = await api.drafts.list(nudge.application_id);
      return drafts.find((d) => d.id === nudge.draft_id) ?? null;
    },
    enabled: Boolean(nudge.draft_id),
  });

  return (
    <li className="ring-card rounded-2xl bg-card p-4">
      <div className="flex items-start gap-3">
        <span className={cn("flex h-9 w-9 shrink-0 items-center justify-center rounded-xl bg-raised", meta?.color)}>
          <Icon size={16} />
        </span>
        <div className="min-w-0 flex-1">
          <div className="flex flex-wrap items-center gap-x-2 gap-y-1">
            <p className="text-sm font-semibold text-ink">{nudge.headline}</p>
            {nudge.rule === "follow_up" && <Chip>touch {nudge.touch}</Chip>}
            <span
              className={cn(
                "inline-flex items-center gap-1 text-[11px]",
                overdue >= 2 ? "text-reject" : "text-ink-3",
              )}
            >
              {overdue >= 2 && <Ghost size={11} />}
              {overdue === 0 ? "due today" : `due ${overdue}d ago`}
            </span>
          </div>
          <p className="mt-1 text-[13px] leading-relaxed text-ink-2">{nudge.detail}</p>

          {draft && (
            <div className="mt-3 rounded-xl border border-line-soft bg-panel p-3">
              <p className="flex items-center gap-1.5 text-[11px] font-medium tracking-wide text-accent uppercase">
                <Sparkles size={11} /> Auto-drafted & ready
              </p>
              {draft.subject && <p className="mt-1.5 text-[13px] font-medium text-ink">{draft.subject}</p>}
              <p className="mt-1 line-clamp-2 text-[13px] text-ink-2">{draft.contents}</p>
            </div>
          )}

          <div className="mt-3 flex flex-wrap items-center gap-2">
            <Link to={`/pipeline?app=${nudge.application_id}`}>
              <Button variant="outline" className="!px-3 !py-1.5">
                Open application
              </Button>
            </Link>
            <Button variant="ghost" className="!px-3 !py-1.5 text-offer" onClick={() => onAct("done")}>
              <Check size={13} /> Done
            </Button>
            <Button variant="ghost" className="!px-3 !py-1.5" onClick={() => onAct("dismiss")}>
              <X size={13} /> Dismiss
            </Button>
            <a
              href={calendarEventUrl({
                title: nudge.headline,
                start: new Date(),
                durationMinutes: 30,
                details: nudge.detail,
              })}
              target="_blank"
              rel="noreferrer"
              className="ml-auto inline-flex items-center gap-1 rounded-lg px-2 py-1.5 text-xs text-ink-3 transition-colors hover:text-accent"
              title="Block 30 minutes for this in Google Calendar"
            >
              <CalendarPlus size={12} /> Block time
            </a>
          </div>
        </div>
      </div>
    </li>
  );
}
