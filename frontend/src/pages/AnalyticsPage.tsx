import { useQuery } from "@tanstack/react-query";
import { BellRing, Send } from "lucide-react";

import { api } from "../api";
import { useAuth } from "../auth";
import { FunnelChart } from "../components/charts/FunnelChart";
import { StatTile } from "../components/charts/StatTile";
import { WeeklyActivity } from "../components/charts/WeeklyActivity";
import { Spinner } from "../components/ui";

export default function AnalyticsPage() {
  const { config } = useAuth();
  const { data, isLoading } = useQuery({ queryKey: ["analytics"], queryFn: api.analytics });

  if (isLoading || !data) {
    return (
      <div className="flex h-full items-center justify-center">
        <Spinner />
      </div>
    );
  }

  const backoff = config?.cadence.follow_up_backoff_days ?? [];

  return (
    <div className="animate-rise mx-auto max-w-5xl px-6 py-6">
      <header className="mb-6">
        <h1 className="font-display text-xl font-bold tracking-tight">Analytics</h1>
        <p className="text-[13px] text-ink-2">Your search, measured like a sales funnel.</p>
      </header>

      <div className="grid grid-cols-2 gap-3 lg:grid-cols-4">
        <StatTile
          label="Interview rate"
          value={`${data.interview_rate}%`}
          sub={`${data.reached_interview} of ${data.total_applications} applications`}
        />
        <StatTile
          label="Offer rate"
          value={`${data.offer_rate}%`}
          sub={`${data.reached_offer} offer${data.reached_offer === 1 ? "" : "s"} from interviews`}
          tone={data.reached_offer > 0 ? "good" : undefined}
        />
        <StatTile
          label="Days to interview"
          value={data.median_days_to_interview === null ? "—" : `${data.median_days_to_interview}`}
          sub="median, from application"
        />
        <StatTile
          label="Ghost rate"
          value={`${data.ghost_rate}%`}
          sub={`${data.ghosted} of ${data.by_status.applied} still-applied, quiet 21+ days`}
          tone={data.ghost_rate > 30 ? "bad" : undefined}
        />
      </div>

      <div className="mt-4 grid gap-4 lg:grid-cols-2">
        <section className="ring-card rounded-2xl bg-card p-5">
          <h2 className="font-display mb-4 text-sm font-semibold tracking-wide">Conversion funnel</h2>
          <FunnelChart
            total={data.total_applications}
            interview={data.reached_interview}
            offer={data.reached_offer}
          />
        </section>

        <section className="ring-card rounded-2xl bg-card p-5">
          <h2 className="font-display mb-4 text-sm font-semibold tracking-wide">Cadence discipline</h2>
          <div className="space-y-4">
            <div className="flex items-center gap-3">
              <span className="flex h-9 w-9 items-center justify-center rounded-lg bg-raised text-accent">
                <Send size={15} />
              </span>
              <div className="flex-1">
                <p className="text-sm font-medium">
                  {data.drafts_sent} of {data.drafts_total} drafts sent
                </p>
                <div className="mt-1.5 h-1.5 rounded-full bg-raised">
                  <div
                    className="h-1.5 rounded-full bg-accent"
                    style={{ width: `${data.drafts_total ? (data.drafts_sent / data.drafts_total) * 100 : 0}%` }}
                  />
                </div>
              </div>
            </div>
            <div className="flex items-center gap-3">
              <span className="flex h-9 w-9 items-center justify-center rounded-lg bg-raised text-accent">
                <BellRing size={15} />
              </span>
              <div className="flex-1">
                <p className="text-sm font-medium">
                  {data.nudges_actioned} nudge{data.nudges_actioned === 1 ? "" : "s"} actioned ·{" "}
                  {data.nudges_pending} waiting
                </p>
                <p className="text-xs text-ink-2">Acting on nudges is what moves the funnel.</p>
              </div>
            </div>
            <div className="rounded-xl border border-line-soft bg-panel p-3">
              <p className="text-[11px] font-medium tracking-wide text-ink-3 uppercase">Your follow-up cadence</p>
              <p className="mt-1 text-sm text-ink-2">
                {backoff.map((days, index) => (
                  <span key={index}>
                    {index > 0 && <span className="text-ink-3"> → </span>}
                    <span className="font-medium text-ink">touch {index + 1}</span> after {days} quiet days
                  </span>
                ))}
              </p>
            </div>
          </div>
        </section>
      </div>

      <section className="ring-card mt-4 rounded-2xl bg-card p-5">
        <h2 className="font-display mb-1 text-sm font-semibold tracking-wide">Weekly momentum</h2>
        <p className="mb-4 text-xs text-ink-2">Applications logged, drafts written, and stage moves — last 8 weeks.</p>
        <WeeklyActivity weeks={data.weekly} />
      </section>
    </div>
  );
}
