import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import {
  Anchor,
  Check,
  ChevronDown,
  Copy,
  FileText,
  KeyRound,
  Mail,
  Send,
  Sparkles,
  Trash2,
  X,
} from "lucide-react";
import { useEffect, useState } from "react";
import { Link } from "react-router-dom";

import { ApiError, api } from "../../api";
import { cn, daysSince, longDate, timeAgo } from "../../lib/format";
import { STATUSES, STATUS_LABEL, type Draft, type DraftType, type Status } from "../../types";
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

  const remove = useMutation({
    mutationFn: () => api.applications.remove(applicationId),
    onSuccess: () => {
      toast("Application deleted", "info");
      invalidate();
      onClose();
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

        <div className="mt-3 grid grid-cols-2 gap-2">
          <GenerateButton
            icon={<FileText size={14} />}
            label="Cover letter"
            model="Gemini 3.1 Pro"
            busy={generate.isPending && generate.variables === "cover_letter"}
            onClick={() => generate.mutate("cover_letter")}
            disabled={generate.isPending}
          />
          <GenerateButton
            icon={<Mail size={14} />}
            label="Follow-up email"
            model="Gemini 3.7 Flash"
            busy={generate.isPending && generate.variables === "follow_up_email"}
            onClick={() => generate.mutate("follow_up_email")}
            disabled={generate.isPending}
          />
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
            <DraftItem key={draft.id} draft={draft} onChanged={invalidate} />
          ))}
        </div>
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
      <aside className="ring-card animate-rise absolute top-0 right-0 h-full w-full max-w-[540px] overflow-y-auto bg-panel p-6">
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
        {busy ? "Writing…" : `Write ${label.toLowerCase()}`}
      </span>
      <span className="mt-1 flex items-center gap-1.5 text-[11px] text-ink-3">
        {icon} {model}
      </span>
    </button>
  );
}

function DraftItem({ draft, onChanged }: { draft: Draft; onChanged: () => void }) {
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

  const isEmail = draft.type === "follow_up_email";

  return (
    <article className="rounded-xl border border-line-soft bg-card">
      <button
        onClick={() => setOpen((current) => !current)}
        className="flex w-full cursor-pointer items-center gap-2.5 p-3 text-left"
      >
        <span className="flex h-7 w-7 shrink-0 items-center justify-center rounded-lg bg-raised text-ink-2">
          {isEmail ? <Mail size={13} /> : <FileText size={13} />}
        </span>
        <span className="min-w-0 flex-1">
          <span className="block truncate text-sm font-medium text-ink">
            {isEmail ? draft.subject || "Follow-up email" : "Cover letter"}
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
          <div className="mt-2 flex items-center gap-2">
            {dirty && (
              <Button variant="primary" className="!px-3 !py-1.5" onClick={() => update.mutate({ contents: text })}>
                <Check size={13} /> Save
              </Button>
            )}
            <Button variant="outline" className="!px-3 !py-1.5" onClick={() => void copy()}>
              <Copy size={13} /> Copy
            </Button>
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
        </div>
      )}
    </article>
  );
}
