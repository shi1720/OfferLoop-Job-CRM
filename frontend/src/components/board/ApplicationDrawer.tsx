import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import {
  Anchor,
  BrainCircuit,
  CalendarPlus,
  Check,
  ChevronDown,
  Copy,
  ExternalLink,
  FileText,
  KeyRound,
  MessageSquareText,
  Mail,
  RefreshCw,
  Send,
  Sparkles,
  Trash2,
  UserRound,
  UserRoundPlus,
  X,
} from "lucide-react";
import { useEffect, useState } from "react";
import { Link } from "react-router-dom";

import { ApiError, api } from "../../api";
import { cn, daysSince, longDate, timeAgo } from "../../lib/format";
import { calendarEventUrl, gmailComposeUrl } from "../../lib/links";
import {
  DRAFT_TYPE_LABEL,
  STATUSES,
  STATUS_LABEL,
  type Application,
  type Draft,
  type DraftType,
  type Status,
} from "../../types";
import { useToast } from "../Toast";
import { Button, Chip, Spinner, STATUS_DOT, inputClass } from "../ui";

export function ApplicationDrawer({ applicationId, onClose }: { applicationId: string; onClose: () => void }) {
  const queryClient = useQueryClient();
  const toast = useToast();

  const { data: app } = useQuery({
    queryKey: ["application", applicationId],
    queryFn: () => api.applications.get(applicationId),
  });
  const { data: drafts } = useQuery({
    queryKey: ["drafts", applicationId],
    queryFn: () => api.drafts.list(applicationId),
  });

  const [notes, setNotes] = useState<string | null>(null);
  const [instructions, setInstructions] = useState("");
  const [engineError, setEngineError] = useState<{ code: string; message: string } | null>(null);
  useEffect(() => {
    const onKey = (event: KeyboardEvent) => event.key === "Escape" && onClose();
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [onClose]);

  const invalidate = () => {
    void queryClient.invalidateQueries({ queryKey: ["applications"] });
    void queryClient.invalidateQueries({ queryKey: ["application", applicationId] });
    void queryClient.invalidateQueries({ queryKey: ["drafts"] });
    void queryClient.invalidateQueries({ queryKey: ["profile"] }); // momentum + free allowance
  };

  const setStatus = useMutation({
    mutationFn: (status: Status) => api.applications.setStatus(applicationId, status),
    onSuccess: (updated) => {
      toast(`Moved to ${STATUS_LABEL[updated.status]}`);
      invalidate();
    },
  });

  const generate = useMutation({
    mutationFn: (type: DraftType) => api.drafts.generate(applicationId, type, instructions.trim()),
    onSuccess: (draft) => {
      setEngineError(null);
      toast(
        draft.grounded_on.length > 0
          ? `Draft ready — grounded on ${draft.grounded_on.length} of your past drafts`
          : "Draft ready",
      );
      invalidate();
    },
    onError: (error) => {
      // Structured engine errors get an inline banner with a fix, not just a toast.
      if (error instanceof ApiError && error.code && (error.code === "key_required" || error.code.startsWith("gemini_"))) {
        setEngineError({ code: error.code, message: error.message });
      } else {
        toast(error.message, "err");
      }
    },
  });

  const saveNotes = useMutation({
    mutationFn: (value: string) => api.applications.update(applicationId, { notes: value }),
    onSuccess: () => invalidate(),
  });

  const prep = useMutation({
    mutationFn: () => api.applications.prep(applicationId),
    onSuccess: () => {
      setEngineError(null);
      toast("Prep pack ready — grounded on this posting and your profile");
      invalidate();
    },
    onError: (error) => {
      if (error instanceof ApiError && error.code && (error.code === "key_required" || error.code.startsWith("gemini_"))) {
        setEngineError({ code: error.code, message: error.message });
      } else {
        toast(error.message, "err");
      }
    },
  });

  const remove = useMutation({
    mutationFn: () => api.applications.remove(applicationId),
    onSuccess: () => {
      invalidate();
      onClose();
      // Soft delete server-side — the Undo restores everything, drafts included.
      toast("Application deleted", "info", {
        label: "Undo",
        onClick: () => {
          void api.applications.restore(applicationId).then(() => {
            invalidate();
            toast("Restored — drafts and history intact");
          });
        },
      });
    },
  });

  if (!app) {
    return (
      <DrawerShell onClose={onClose}>
        <div className="flex h-40 items-center justify-center">
          <Spinner />
        </div>
      </DrawerShell>
    );
  }

  const quiet = daysSince(app.last_activity_at);

  return (
    <DrawerShell onClose={onClose}>
      {/* Header */}
      <header className="flex items-start justify-between gap-4">
        <div className="min-w-0">
          <h2 className="font-display text-xl leading-tight font-bold tracking-tight">{app.role}</h2>
          <p className="mt-1 text-sm text-ink-2">
            {app.company || <span className="italic">Confidential</span>}
            {app.location && <span className="text-ink-3"> · {app.location}</span>}
            {app.posting_url && (
              <a
                href={app.posting_url}
                target="_blank"
                rel="noreferrer"
                className="ml-2 inline-flex items-center gap-0.5 text-xs text-accent hover:underline"
              >
                View posting <ExternalLink size={10} />
              </a>
            )}
          </p>
        </div>
        <button
          onClick={onClose}
          aria-label="Close details"
          className="cursor-pointer rounded-lg p-1.5 text-ink-3 transition-colors hover:bg-raised hover:text-ink"
        >
          <X size={18} />
        </button>
      </header>

      {/* Stage switcher */}
      <div className="mt-4 flex gap-1.5">
        {STATUSES.map((status) => (
          <button
            key={status}
            onClick={() => status !== app.status && setStatus.mutate(status)}
            className={cn(
              "flex-1 cursor-pointer rounded-lg border px-2 py-1.5 text-xs font-medium transition-all",
              status === app.status
                ? "border-accent/50 bg-accent/10 text-accent"
                : "border-line text-ink-3 hover:border-ink-3 hover:text-ink",
            )}
          >
            {STATUS_LABEL[status]}
          </button>
        ))}
      </div>

      {/* Meta */}
      <dl className="mt-5 grid grid-cols-3 gap-3 rounded-xl border border-line-soft bg-card p-4 text-sm">
        <MetaItem label="Applied" value={longDate(app.applied_at)} />
        <MetaItem
          label="Quiet for"
          value={quiet === 0 ? "Active today" : `${quiet} day${quiet > 1 ? "s" : ""}`}
          tone={quiet >= 10 ? "hot" : quiet >= 5 ? "warm" : undefined}
        />
        <MetaItem label="Type" value={app.job_type || "—"} />
      </dl>
      {app.skills.length > 0 && (
        <div className="mt-3 flex flex-wrap gap-1.5">
          {app.skills.map((skill) => (
            <Chip key={skill}>{skill}</Chip>
          ))}
          {app.source === "import" && <Chip className="text-accent">imported from CSV #{app.external_id}</Chip>}
        </div>
      )}

      <ContactAndInterview app={app} onChanged={invalidate} />
      {app.description && (
        <details className="group mt-3">
          <summary className="flex cursor-pointer items-center gap-1 text-xs font-medium text-ink-3 select-none hover:text-ink-2">
            <ChevronDown size={13} className="transition-transform group-open:rotate-180" />
            Posting description
          </summary>
          <p className="mt-2 rounded-lg border border-line-soft bg-card p-3 text-[13px] leading-relaxed whitespace-pre-wrap text-ink-2">
            {app.description}
          </p>
        </details>
      )}

      {/* Drafts */}
      <section className="mt-6">
        <div className="flex items-center justify-between">
          <h3 className="font-display text-sm font-semibold tracking-wide">Outreach drafts</h3>
          <span className="text-xs text-ink-3">{drafts?.length ?? 0} total</span>
        </div>

        {engineError && (
          <div
            role="alert"
            className="mt-3 flex items-start gap-2.5 rounded-xl border border-reject/40 bg-reject/5 px-3.5 py-3"
          >
            <KeyRound size={14} className="mt-0.5 shrink-0 text-reject" />
            <div className="min-w-0 text-[13px]">
              <p className="text-ink">{engineError.message}</p>
              {(engineError.code === "key_required" ||
                engineError.code === "gemini_key_invalid" ||
                engineError.code === "gemini_quota_exhausted") && (
                <Link to="/profile" className="mt-1 inline-block font-medium text-accent hover:underline">
                  {engineError.code === "key_required" ? "Add your free Gemini key →" : "Manage your key →"}
                </Link>
              )}
            </div>
          </div>
        )}

        <div className="mt-3 grid grid-cols-1 gap-2 sm:grid-cols-2">
          {(
            [
              { type: "cover_letter", icon: <FileText size={14} />, model: "Gemini 3.1 Pro", action: "Write cover letter" },
              { type: "follow_up_email", icon: <Mail size={14} />, model: "Gemini 3.7 Flash", action: "Write follow-up email" },
              { type: "referral_request", icon: <UserRoundPlus size={14} />, model: "Gemini 3.7 Flash", action: "Request a referral" },
              { type: "linkedin_message", icon: <MessageSquareText size={14} />, model: "Gemini 3.7 Flash", action: "Write LinkedIn DM" },
            ] as { type: DraftType; icon: React.ReactNode; model: string; action: string }[]
          ).map(({ type, icon, model, action }) => (
            <GenerateButton
              key={type}
              icon={icon}
              label={action}
              model={model}
              busy={generate.isPending && generate.variables === type}
              onClick={() => generate.mutate(type)}
              disabled={generate.isPending}
            />
          ))}
        </div>
        <input
          className={`${inputClass} mt-2`}
          placeholder="Optional: steer this draft — e.g. mention the referral from Priya, lead with the Kafka work"
          value={instructions}
          onChange={(event) => setInstructions(event.target.value)}
        />
        <p className="mt-1.5 text-[11px] text-ink-3">
          Permanent rules (e.g. "never use em dashes") live in{" "}
          <Link to="/profile" className="text-accent hover:underline">
            Profile → Writing rules
          </Link>{" "}
          and apply to every draft.
        </p>

        <div className="mt-3 space-y-2">
          {(drafts ?? []).map((draft) => (
            <DraftItem key={draft.id} draft={draft} app={app} onChanged={invalidate} />
          ))}
        </div>
      </section>

      {/* Interview prep */}
      <section className="mt-6">
        <div className="flex items-center justify-between gap-2">
          <h3 className="font-display text-sm font-semibold tracking-wide">Interview prep</h3>
          <Button
            variant="outline"
            className="!px-3 !py-1.5"
            onClick={() => prep.mutate()}
            disabled={prep.isPending}
          >
            {prep.isPending ? <Spinner /> : app.prep_pack ? <RefreshCw size={13} /> : <BrainCircuit size={13} />}
            {prep.isPending ? "Preparing…" : app.prep_pack ? "Regenerate" : "Build prep pack"}
          </Button>
        </div>
        {app.prep_pack ? (
          <PrepPackView pack={app.prep_pack} />
        ) : (
          <p className="mt-2 text-[13px] text-ink-2">
            Likely questions for this exact posting, STAR stories built from your own proof points, and sharp
            questions to ask back{app.status === "interview" ? " — you're in the loop, build it now." : "."}
          </p>
        )}
      </section>

      {/* Timeline */}
      <section className="mt-6">
        <h3 className="font-display text-sm font-semibold tracking-wide">Journey</h3>
        <ol className="mt-3 space-y-0">
          {[...app.status_history].reverse().map((change, index, list) => (
            <li key={index} className="relative flex gap-3 pb-4">
              {index < list.length - 1 && (
                <span className="absolute top-4 left-[4.5px] h-full w-px bg-line-soft" aria-hidden />
              )}
              <span className={cn("mt-1.5 h-2.5 w-2.5 shrink-0 rounded-full", STATUS_DOT[change.to_status])} />
              <div className="min-w-0">
                <p className="text-sm text-ink">
                  {change.from_status ? (
                    <>
                      {STATUS_LABEL[change.from_status]} → <strong>{STATUS_LABEL[change.to_status]}</strong>
                    </>
                  ) : (
                    <>
                      Logged as <strong>{STATUS_LABEL[change.to_status]}</strong>
                    </>
                  )}
                </p>
                {change.note && <p className="text-xs text-ink-2 italic">“{change.note}”</p>}
                <p className="text-[11px] text-ink-3">{longDate(change.at)}</p>
              </div>
            </li>
          ))}
        </ol>
      </section>

      {/* Notes */}
      <section className="mt-2">
        <h3 className="font-display text-sm font-semibold tracking-wide">Notes</h3>
        <textarea
          className={`${inputClass} mt-2 min-h-20 resize-y`}
          placeholder="Referrals, recruiter names, interview prep…"
          value={notes ?? app.notes}
          onChange={(event) => setNotes(event.target.value)}
          onBlur={() => {
            if (notes !== null && notes !== app.notes) saveNotes.mutate(notes);
          }}
        />
      </section>

      <div className="mt-6 border-t border-line-soft pt-4">
        <Button
          variant="danger"
          onClick={() => {
            if (window.confirm("Delete this application and all its drafts?")) remove.mutate();
          }}
        >
          <Trash2 size={14} /> Delete application
        </Button>
      </div>
    </DrawerShell>
  );
}

function DrawerShell({ children, onClose }: { children: React.ReactNode; onClose: () => void }) {
  return (
    <div className="fixed inset-0 z-50">
      <div className="absolute inset-0 bg-page/60 backdrop-blur-[2px]" onClick={onClose} />
      <aside className="ring-card animate-rise absolute top-0 right-0 h-full w-full max-w-[540px] overflow-y-auto bg-panel p-4 sm:p-6">
        {children}
      </aside>
    </div>
  );
}

function MetaItem({ label, value, tone }: { label: string; value: string; tone?: "warm" | "hot" }) {
  return (
    <div>
      <dt className="text-[11px] tracking-wide text-ink-3 uppercase">{label}</dt>
      <dd className={cn("mt-0.5 font-medium", tone === "hot" && "text-reject", tone === "warm" && "text-interview")}>
        {value}
      </dd>
    </div>
  );
}

function GenerateButton({
  icon,
  label,
  model,
  busy,
  onClick,
  disabled,
}: {
  icon: React.ReactNode;
  label: string;
  model: string;
  busy: boolean;
  onClick: () => void;
  disabled: boolean;
}) {
  return (
    <button
      onClick={onClick}
      disabled={disabled}
      className="group cursor-pointer rounded-xl border border-line bg-card p-3 text-left transition-all hover:border-accent/40 hover:bg-raised disabled:cursor-not-allowed disabled:opacity-50"
    >
      <span className="flex items-center gap-2 text-sm font-medium text-ink">
        {busy ? <Spinner /> : <Sparkles size={14} className="text-accent" />}
        {busy ? "Writing…" : label}
      </span>
      <span className="mt-1 flex items-center gap-1.5 text-[11px] text-ink-3">
        {icon} {model}
      </span>
    </button>
  );
}

function DraftItem({ draft, app, onChanged }: { draft: Draft; app: Application; onChanged: () => void }) {
  const toast = useToast();
  const [open, setOpen] = useState(draft.status === "draft" && draft.source === "generated");
  const [text, setText] = useState(draft.contents);
  const dirty = text !== draft.contents;

  const update = useMutation({
    mutationFn: (payload: { contents?: string; status?: "draft" | "sent" }) => api.drafts.update(draft.id, payload),
    onSuccess: (_, payload) => {
      toast(payload.status === "sent" ? "Marked sent — +15 momentum, staleness clock reset" : "Draft saved");
      onChanged();
    },
  });

  const copy = async () => {
    await navigator.clipboard.writeText(draft.subject ? `Subject: ${draft.subject}\n\n${text}` : text);
    toast("Copied to clipboard", "info");
  };

  const typeIcon = {
    cover_letter: <FileText size={13} />,
    follow_up_email: <Mail size={13} />,
    referral_request: <UserRoundPlus size={13} />,
    linkedin_message: <MessageSquareText size={13} />,
  }[draft.type];

  return (
    <article className="rounded-xl border border-line-soft bg-card">
      <button
        onClick={() => setOpen((current) => !current)}
        className="flex w-full cursor-pointer items-center gap-2.5 p-3 text-left"
      >
        <span className="flex h-7 w-7 shrink-0 items-center justify-center rounded-lg bg-raised text-ink-2">
          {typeIcon}
        </span>
        <span className="min-w-0 flex-1">
          <span className="block truncate text-sm font-medium text-ink">
            {draft.subject || DRAFT_TYPE_LABEL[draft.type]}
          </span>
          <span className="mt-0.5 flex flex-wrap items-center gap-x-2 gap-y-0.5 text-[11px] text-ink-3">
            <span>{timeAgo(draft.created_at)}</span>
            {draft.model && draft.model !== "template" && <span className="text-applied">{draft.model}</span>}
            {draft.source === "imported" && <span>imported</span>}
            {draft.source === "edited" && <span>edited</span>}
            {draft.grounded_on.length > 0 && (
              <span className="inline-flex items-center gap-1 text-accent">
                <Anchor size={10} />
                grounded on {draft.grounded_on.length} past draft{draft.grounded_on.length > 1 ? "s" : ""}
              </span>
            )}
          </span>
        </span>
        <span
          className={cn(
            "rounded-full px-2 py-0.5 text-[10px] font-semibold tracking-wide uppercase",
            draft.status === "sent" ? "bg-offer/10 text-offer" : "bg-raised text-ink-3",
          )}
        >
          {draft.status}
        </span>
        <ChevronDown size={14} className={cn("shrink-0 text-ink-3 transition-transform", open && "rotate-180")} />
      </button>

      {open && (
        <div className="border-t border-line-soft p-3">
          <textarea
            className={`${inputClass} min-h-44 resize-y font-[13px] leading-relaxed`}
            value={text}
            onChange={(event) => setText(event.target.value)}
          />
          <div className="mt-2 flex flex-wrap items-center gap-2">
            {dirty && (
              <Button variant="primary" className="!px-3 !py-1.5" onClick={() => update.mutate({ contents: text })}>
                <Check size={13} /> Save
              </Button>
            )}
            <Button variant="outline" className="!px-3 !py-1.5" onClick={() => void copy()}>
              <Copy size={13} /> Copy
            </Button>
            {draft.type !== "linkedin_message" && (
              <a
                href={gmailComposeUrl({
                  to: app.contact_email || undefined,
                  subject: draft.subject || `Regarding my ${app.role} application`,
                  body: text,
                })}
                target="_blank"
                rel="noreferrer"
                className="inline-flex cursor-pointer items-center gap-1.5 rounded-lg border border-line px-3 py-1.5 text-sm font-medium text-ink transition-all hover:border-ink-3 hover:bg-raised"
              >
                <Mail size={13} /> Open in Gmail
              </a>
            )}
            {draft.status === "draft" && (
              <Button
                variant="outline"
                className="ml-auto !px-3 !py-1.5 text-offer"
                onClick={() => update.mutate({ status: "sent" })}
              >
                <Send size={13} /> Mark sent
              </Button>
            )}
          </div>
          {draft.type !== "linkedin_message" && !app.contact_email && (
            <p className="mt-1.5 text-[11px] text-ink-3">
              Tip: add a contact email above and Gmail opens pre-addressed.
            </p>
          )}
        </div>
      )}
    </article>
  );
}

/** Recruiter contact + next-interview panel: the "who" and "when" a CRM
 * runs on. Saves on blur; the calendar link needs no OAuth. */
function ContactAndInterview({ app, onChanged }: { app: Application; onChanged: () => void }) {
  const toast = useToast();
  const [name, setName] = useState<string | null>(null);
  const [email, setEmail] = useState<string | null>(null);
  const [when, setWhen] = useState<string | null>(null);

  const save = useMutation({
    mutationFn: (patch: Record<string, unknown>) => api.applications.update(app.id, patch),
    onSuccess: () => onChanged(),
    onError: (error) => toast(error.message, "err"),
  });

  // datetime-local wants local time without the Z
  const localValue = (iso: string | null) => {
    if (!iso) return "";
    const date = new Date(iso);
    const pad = (n: number) => String(n).padStart(2, "0");
    return `${date.getFullYear()}-${pad(date.getMonth() + 1)}-${pad(date.getDate())}T${pad(date.getHours())}:${pad(date.getMinutes())}`;
  };

  const interviewDate = app.interview_at ? new Date(app.interview_at) : null;

  return (
    <div className="mt-3 rounded-xl border border-line-soft bg-card p-4">
      <div className="grid grid-cols-1 gap-3 sm:grid-cols-2">
        <label className="block">
          <span className="flex items-center gap-1 text-[11px] tracking-wide text-ink-3 uppercase">
            <UserRound size={10} /> Contact
          </span>
          <input
            className={`${inputClass} mt-1`}
            placeholder="Recruiter / referrer name"
            value={name ?? app.contact_name}
            onChange={(event) => setName(event.target.value)}
            onBlur={() => {
              if (name !== null && name !== app.contact_name) save.mutate({ contact_name: name });
            }}
          />
        </label>
        <label className="block">
          <span className="text-[11px] tracking-wide text-ink-3 uppercase">Contact email</span>
          <input
            className={`${inputClass} mt-1`}
            type="email"
            placeholder="name@company.com"
            value={email ?? app.contact_email}
            onChange={(event) => setEmail(event.target.value)}
            onBlur={() => {
              if (email !== null && email !== app.contact_email) save.mutate({ contact_email: email });
            }}
          />
        </label>
      </div>
      <div className="mt-3 flex flex-wrap items-end gap-2">
        <label className="block min-w-0 flex-1">
          <span className="flex items-center gap-1 text-[11px] tracking-wide text-ink-3 uppercase">
            <CalendarPlus size={10} /> Next interview
          </span>
          <input
            className={`${inputClass} mt-1`}
            type="datetime-local"
            value={when ?? localValue(app.interview_at)}
            onChange={(event) => setWhen(event.target.value)}
            onBlur={() => {
              if (when === null) return;
              if (when === "") {
                save.mutate({ clear_interview: true });
                return;
              }
              const parsed = new Date(when);
              if (Number.isNaN(parsed.getTime())) {
                toast("That date didn't parse — try again", "err");
                return;
              }
              save.mutate({ interview_at: parsed.toISOString() });
            }}
          />
        </label>
        {interviewDate && (
          <a
            href={calendarEventUrl({
              title: `Interview: ${app.role}${app.company ? ` at ${app.company}` : ""}`,
              start: interviewDate,
              details: `Prep pack and notes in OfferLoop.${app.posting_url ? `\nPosting: ${app.posting_url}` : ""}`,
              location: app.location,
            })}
            target="_blank"
            rel="noreferrer"
            className="inline-flex shrink-0 items-center gap-1.5 rounded-lg border border-accent/40 px-3 py-2 text-sm font-medium text-accent transition-colors hover:bg-accent/10"
          >
            <CalendarPlus size={13} /> Add to Calendar
          </a>
        )}
      </div>
    </div>
  );
}

function PrepPackView({ pack }: { pack: NonNullable<Application["prep_pack"]> }) {
  return (
    <div className="mt-3 space-y-2">
      <details className="group rounded-xl border border-line-soft bg-card" open>
        <summary className="cursor-pointer p-3 text-sm font-medium text-ink select-none">
          Likely questions <span className="text-ink-3">({pack.questions.length})</span>
        </summary>
        <ol className="space-y-3 border-t border-line-soft p-3">
          {pack.questions.map((q, i) => (
            <li key={i}>
              <p className="text-sm font-medium text-ink">{q.question}</p>
              {q.why_they_ask && <p className="mt-0.5 text-xs text-ink-3 italic">Why: {q.why_they_ask}</p>}
              {q.how_to_answer && <p className="mt-0.5 text-[13px] text-ink-2">→ {q.how_to_answer}</p>}
            </li>
          ))}
        </ol>
      </details>
      <details className="group rounded-xl border border-line-soft bg-card">
        <summary className="cursor-pointer p-3 text-sm font-medium text-ink select-none">
          Your stories <span className="text-ink-3">({pack.stories.length})</span>
        </summary>
        <div className="space-y-3 border-t border-line-soft p-3">
          {pack.stories.map((story, i) => (
            <div key={i}>
              <p className="text-sm font-medium text-accent">{story.title}</p>
              <p className="mt-0.5 text-[13px] text-ink-2">{story.outline}</p>
              {story.metric && <p className="mt-0.5 text-xs text-offer">Land the number: {story.metric}</p>}
            </div>
          ))}
        </div>
      </details>
      <details className="group rounded-xl border border-line-soft bg-card">
        <summary className="cursor-pointer p-3 text-sm font-medium text-ink select-none">
          Ask them <span className="text-ink-3">({pack.questions_to_ask.length})</span>
        </summary>
        <ul className="list-disc space-y-1.5 border-t border-line-soft p-3 pl-7 text-[13px] text-ink-2">
          {pack.questions_to_ask.map((q, i) => (
            <li key={i}>{q}</li>
          ))}
        </ul>
      </details>
      <p className="text-[11px] text-ink-3">
        Built from this posting and your profile{pack.model && pack.model !== "template" ? ` by ${pack.model}` : ""} ·
        facts only, nothing invented.
      </p>
    </div>
  );
}
