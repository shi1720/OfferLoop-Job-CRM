/** Today — the landing page and daily ritual. The board is the map;
 * this is the to-do list: follow-ups due now, interviews coming up,
 * applications going quiet, and the weekly goal that keeps the search
 * moving. Everything links straight into the pipeline. */

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import {
  ArrowRight,
  BellRing,
  CalendarPlus,
  CheckCircle2,
  Flame,
  Minus,
  Plus,
  Radar,
  Send,
} from "lucide-react";
import { useMemo } from "react";
import { Link, useNavigate } from "react-router-dom";

import { api } from "../api";
import { useAuth } from "../auth";
import { PushPrompt } from "../components/AccountCards";
import { useToast } from "../components/Toast";
import { Button, Spinner } from "../components/ui";
import { cn, daysSince, timeAgo } from "../lib/format";
import { calendarEventUrl } from "../lib/links";
import type { Application, Nudge } from "../types";

function greeting(): string {
  const hour = new Date().getHours();
  if (hour < 12) return "Good morning";
  if (hour < 17) return "Good afternoon";
  return "Good evening";
}

function weekStart(): Date {
  const now = new Date();
  const monday = new Date(now);
  monday.setDate(now.getDate() - ((now.getDay() + 6) % 7));
  monday.setHours(0, 0, 0, 0);
  return monday;
}

export default function TodayPage() {
  const { user } = useAuth();
  const navigate = useNavigate();
  const queryClient = useQueryClient();
  const toast = useToast();

  const { data: apps } = useQuery({ queryKey: ["applications"], queryFn: api.applications.list });
  const { data: nudges } = useQuery({
    queryKey: ["nudges", "pending"],
    queryFn: () => api.nudges.list("pending"),
    refetchInterval: 60_000,
  });
  const { data: profile } = useQuery({ queryKey: ["profile"], queryFn: api.profile.get });

  const appById = useMemo(() => new Map((apps ?? []).map((a) => [a.id, a])), [apps]);
  const now = Date.now();

  const dueNudges = useMemo(
    () =>
      (nudges ?? [])
        .filter((n) => new Date(n.due_at).getTime() <= now && appById.has(n.application_id))
        .sort((a, b) => new Date(a.due_at).getTime() - new Date(b.due_at).getTime())
        .slice(0, 5),
    [nudges, appById, now],
  );

  const upcomingInterviews = useMemo(
    () =>
      (apps ?? [])
        .filter((a) => a.interview_at && new Date(a.interview_at).getTime() > now - 3_600_000)
        .sort((a, b) => new Date(a.interview_at!).getTime() - new Date(b.interview_at!).getTime())
        .slice(0, 4),
    [apps, now],
  );

  const goingQuiet = useMemo(
    () =>
      (apps ?? [])
        .filter((a) => a.status === "applied" && daysSince(a.last_activity_at) >= 5)
        .sort((a, b) => daysSince(b.last_activity_at) - daysSince(a.last_activity_at))
        .slice(0, 5),
    [apps],
  );

  const loggedThisWeek = useMemo(() => {
    const start = weekStart().getTime();
    return (apps ?? []).filter((a) => new Date(a.applied_at).getTime() >= start).length;
  }, [apps]);

  const setGoal = useMutation({
    mutationFn: (weekly_goal: number) => api.profile.update({ weekly_goal }),
    onSuccess: () => void queryClient.invalidateQueries({ queryKey: ["profile"] }),
  });

  const nudgeDone = useMutation({
    mutationFn: (id: string) => api.nudges.done(id),
    onSuccess: () => {
      toast("Done — +20 momentum");
      void queryClient.invalidateQueries({ queryKey: ["nudges"] });
      void queryClient.invalidateQueries({ queryKey: ["profile"] });
    },
  });

  const scan = useMutation({
    mutationFn: api.scan,
    onSuccess: (report) => {
      toast(
        report.nudges_created > 0
          ? `${report.nudges_created} new nudge${report.nudges_created > 1 ? "s" : ""} found, ${report.drafts_generated} draft${report.drafts_generated === 1 ? "" : "s"} written`
          : "Pipeline scanned — you're on top of everything",
        "info",
      );
      void queryClient.invalidateQueries({ queryKey: ["nudges"] });
      void queryClient.invalidateQueries({ queryKey: ["drafts"] });
    },
  });

  if (!apps || !profile) {
    return (
      <div className="flex h-full items-center justify-center">
        <Spinner />
      </div>
    );
  }

  const firstName = (user?.name ?? "").split(" ")[0] || "there";
  const goal = Math.max(1, profile.weekly_goal || 5);
  const goalPct = Math.min(100, Math.round((loggedThisWeek / goal) * 100));

  return (
    <div className="animate-rise mx-auto max-w-4xl px-4 py-6 sm:px-6">
      <header className="mb-5">
        <h1 className="font-display text-xl font-bold tracking-tight">
          {greeting()}, {firstName}
        </h1>
        <p className="text-[13px] text-ink-2">
          {new Date().toLocaleDateString(undefined, { weekday: "long", month: "long", day: "numeric" })} ·{" "}
          {dueNudges.length > 0
            ? `${dueNudges.length} follow-up${dueNudges.length > 1 ? "s" : ""} due — drafts are ready`
            : "no follow-ups due right now"}
        </p>
      </header>

      <PushPrompt />

      <div className="grid grid-cols-1 gap-4 lg:grid-cols-3">
        {/* Weekly goal */}
        <section className="ring-card rounded-2xl bg-card p-5">
          <div className="flex items-center justify-between">
            <h2 className="font-display flex items-center gap-1.5 text-sm font-bold tracking-wide">
              <Flame size={14} className="text-accent" /> This week
            </h2>
            <div className="flex items-center gap-1">
              <button
                aria-label="Lower weekly goal"
                onClick={() => profile.weekly_goal > 1 && setGoal.mutate(profile.weekly_goal - 1)}
                className="cursor-pointer rounded-md p-1 text-ink-3 transition-colors hover:bg-raised hover:text-ink"
              >
                <Minus size={12} />
              </button>
              <span className="min-w-6 text-center text-xs text-ink-2">{goal}</span>
              <button
                aria-label="Raise weekly goal"
                onClick={() => setGoal.mutate(profile.weekly_goal + 1)}
                className="cursor-pointer rounded-md p-1 text-ink-3 transition-colors hover:bg-raised hover:text-ink"
              >
                <Plus size={12} />
              </button>
            </div>
          </div>
          <p className="font-display mt-3 text-3xl font-bold text-ink">
            {loggedThisWeek}
            <span className="text-base font-medium text-ink-3"> / {goal} applications</span>
          </p>
          <div className="mt-2 h-1.5 overflow-hidden rounded-full bg-raised">
            <div
              className={cn("h-full rounded-full transition-all duration-500", goalPct >= 100 ? "bg-offer" : "bg-accent")}
              style={{ width: `${goalPct}%` }}
            />
          </div>
          <p className="mt-2 text-[11px] text-ink-3">
            {goalPct >= 100 ? "Goal hit — momentum compounds. Keep going." : "+10 momentum for every application you log."}
          </p>
          <Link
            to="/pipeline"
            className="mt-3 inline-flex items-center gap-1 text-[13px] font-medium text-accent hover:underline"
          >
            Log or capture one now <ArrowRight size={13} />
          </Link>
        </section>

        {/* Due follow-ups */}
        <section className="ring-card rounded-2xl bg-card p-5 lg:col-span-2">
          <div className="flex items-center justify-between">
            <h2 className="font-display flex items-center gap-1.5 text-sm font-bold tracking-wide">
              <Send size={14} className="text-accent" /> Due follow-ups
            </h2>
            <Button variant="outline" className="!px-3 !py-1.5" onClick={() => scan.mutate()} disabled={scan.isPending}>
              {scan.isPending ? <Spinner /> : <Radar size={13} />} Scan now
            </Button>
          </div>
          {dueNudges.length === 0 ? (
            <p className="mt-3 flex items-center gap-2 text-[13px] text-ink-2">
              <CheckCircle2 size={14} className="text-offer" />
              Nothing due. Every application is worked — that's the whole point.
            </p>
          ) : (
            <ul className="mt-3 space-y-2">
              {dueNudges.map((nudge) => (
                <DueNudgeRow
                  key={nudge.id}
                  nudge={nudge}
                  app={appById.get(nudge.application_id)}
                  onOpen={() => navigate(`/pipeline?app=${nudge.application_id}`)}
                  onDone={() => nudgeDone.mutate(nudge.id)}
                />
              ))}
            </ul>
          )}
        </section>

        {/* Interviews coming up */}
        <section className="ring-card rounded-2xl bg-card p-5 lg:col-span-2">
          <h2 className="font-display flex items-center gap-1.5 text-sm font-bold tracking-wide">
            <CalendarPlus size={14} className="text-accent" /> Interviews coming up
          </h2>
          {upcomingInterviews.length === 0 ? (
            <p className="mt-3 text-[13px] text-ink-2">
              None scheduled. When you set an interview date on a card it lands here — with a prep pack and a
              calendar link ready.
            </p>
          ) : (
            <ul className="mt-3 space-y-2">
              {upcomingInterviews.map((app) => (
                <li
                  key={app.id}
                  className="flex flex-wrap items-center gap-2 rounded-xl border border-line-soft px-3.5 py-2.5"
                >
                  <div className="min-w-0 flex-1">
                    <p className="truncate text-sm font-medium text-ink">
                      {app.role}
                      {app.company && <span className="text-ink-2"> · {app.company}</span>}
                    </p>
                    <p className="text-xs text-interview">
                      {new Date(app.interview_at!).toLocaleString(undefined, {
                        weekday: "short",
                        month: "short",
                        day: "numeric",
                        hour: "numeric",
                        minute: "2-digit",
                      })}
                    </p>
                  </div>
                  <a
                    href={calendarEventUrl({
                      title: `Interview: ${app.role}${app.company ? ` at ${app.company}` : ""}`,
                      start: new Date(app.interview_at!),
                      location: app.location,
                    })}
                    target="_blank"
                    rel="noreferrer"
                    className="inline-flex items-center gap-1 rounded-lg border border-line px-2.5 py-1.5 text-xs text-ink-2 transition-colors hover:border-accent/40 hover:text-accent"
                  >
                    <CalendarPlus size={11} /> Calendar
                  </a>
                  <button
                    onClick={() => navigate(`/pipeline?app=${app.id}`)}
                    className="inline-flex cursor-pointer items-center gap-1 rounded-lg border border-accent/40 px-2.5 py-1.5 text-xs font-medium text-accent transition-colors hover:bg-accent/10"
                  >
                    {app.prep_pack ? "Review prep" : "Build prep"} <ArrowRight size={11} />
                  </button>
                </li>
              ))}
            </ul>
          )}
        </section>

        {/* Going quiet */}
        <section className="ring-card rounded-2xl bg-card p-5">
          <h2 className="font-display flex items-center gap-1.5 text-sm font-bold tracking-wide">
            <BellRing size={14} className="text-accent" /> Going quiet
          </h2>
          {goingQuiet.length === 0 ? (
            <p className="mt-3 text-[13px] text-ink-2">No application has gone quiet. Watch this space.</p>
          ) : (
            <ul className="mt-3 space-y-1.5">
              {goingQuiet.map((app) => (
                <li key={app.id}>
                  <button
                    onClick={() => navigate(`/pipeline?app=${app.id}`)}
                    className="flex w-full cursor-pointer items-center gap-2 rounded-lg px-2 py-1.5 text-left transition-colors hover:bg-raised"
                  >
                    <span className="min-w-0 flex-1 truncate text-[13px] text-ink">
                      {app.role}
                      {app.company && <span className="text-ink-3"> · {app.company}</span>}
                    </span>
                    <span
                      className={cn(
                        "shrink-0 text-[11px] font-medium",
                        daysSince(app.last_activity_at) >= 10 ? "text-reject" : "text-interview",
                      )}
                    >
                      {daysSince(app.last_activity_at)}d quiet
                    </span>
                  </button>
                </li>
              ))}
            </ul>
          )}
        </section>
      </div>
    </div>
  );
}

function DueNudgeRow({
  nudge,
  app,
  onOpen,
  onDone,
}: {
  nudge: Nudge;
  app: Application | undefined;
  onOpen: () => void;
  onDone: () => void;
}) {
  return (
    <li className="flex flex-wrap items-center gap-2 rounded-xl border border-line-soft px-3.5 py-2.5">
      <div className="min-w-0 flex-1 basis-52">
        <p className="line-clamp-2 text-sm font-medium break-words text-ink">{nudge.headline}</p>
        <p className="text-xs text-ink-3">
          due {timeAgo(nudge.due_at)}
          {nudge.draft_id && <span className="text-accent"> · draft attached</span>}
          {app && app.contact_email && <span> · {app.contact_email}</span>}
        </p>
      </div>
      <button
        onClick={onOpen}
        className="inline-flex cursor-pointer items-center gap-1 rounded-lg border border-accent/40 px-2.5 py-1.5 text-xs font-medium text-accent transition-colors hover:bg-accent/10"
      >
        Open <ArrowRight size={11} />
      </button>
      <button
        onClick={onDone}
        className="inline-flex cursor-pointer items-center gap-1 rounded-lg border border-line px-2.5 py-1.5 text-xs text-ink-2 transition-colors hover:border-offer/50 hover:text-offer"
      >
        <CheckCircle2 size={11} /> Done
      </button>
    </li>
  );
}
