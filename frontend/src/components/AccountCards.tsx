/** Profile-page cards: web-push notifications, data export, and the
 * danger zone. Your data, no lock-in — the launch-day trust story. */

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { AlertTriangle, BellRing, Download, FileDown } from "lucide-react";
import { useState } from "react";

import { api } from "../api";
import { useAuth } from "../auth";
import { enableWebPush, pushSupported } from "../firebase";
import { useToast } from "./Toast";
import { Button, Spinner, inputClass } from "./ui";

export function NotificationsCard() {
  const { config } = useAuth();
  const queryClient = useQueryClient();
  const toast = useToast();
  const { data: profile } = useQuery({ queryKey: ["profile"], queryFn: api.profile.get });
  const [busy, setBusy] = useState(false);

  const available = config?.mode === "live" && Boolean(config.push_vapid_key) && pushSupported();
  if (!available || !profile) return null;

  const refresh = () => void queryClient.invalidateQueries({ queryKey: ["profile"] });

  const enable = async () => {
    setBusy(true);
    try {
      const token = await enableWebPush(config!.firebase, config!.push_vapid_key);
      await api.profile.registerPushToken(token);
      refresh();
      toast("Notifications on — you'll get a ping when follow-ups are due");
    } catch (err) {
      toast(err instanceof Error ? err.message : "Couldn't enable notifications", "err");
    } finally {
      setBusy(false);
    }
  };

  const disable = async () => {
    setBusy(true);
    try {
      await api.profile.disablePush();
      refresh();
      toast("Notifications off", "info");
    } finally {
      setBusy(false);
    }
  };

  return (
    <section className="ring-card mt-5 rounded-2xl bg-card p-6">
      <div className="flex items-center gap-2">
        <BellRing size={15} className="text-accent" />
        <h2 className="font-display text-sm font-bold tracking-wide">Notifications</h2>
      </div>
      <div className="mt-3 flex flex-wrap items-center justify-between gap-3">
        <p className="max-w-md text-[13px] text-ink-2">
          The nudge engine scans hourly. Get a browser ping the moment follow-ups come due — drafts attached,
          nothing to write.
        </p>
        <Button variant={profile.push_enabled ? "outline" : "primary"} disabled={busy} onClick={() => void (profile.push_enabled ? disable() : enable())}>
          {busy ? <Spinner /> : <BellRing size={14} />}
          {profile.push_enabled ? "Turn off" : "Enable notifications"}
        </Button>
      </div>
    </section>
  );
}

/** Slim, dismissable version for the Today page — where the habit forms. */
export function PushPrompt() {
  const { config } = useAuth();
  const queryClient = useQueryClient();
  const toast = useToast();
  const { data: profile } = useQuery({ queryKey: ["profile"], queryFn: api.profile.get });
  const [busy, setBusy] = useState(false);
  const [dismissed, setDismissed] = useState(() => {
    try {
      return localStorage.getItem("offerloop:push-prompt-dismissed") === "1";
    } catch {
      return false;
    }
  });

  const available = config?.mode === "live" && Boolean(config.push_vapid_key) && pushSupported();
  if (!available || !profile || profile.push_enabled || dismissed) return null;

  const enable = async () => {
    setBusy(true);
    try {
      const token = await enableWebPush(config!.firebase, config!.push_vapid_key);
      await api.profile.registerPushToken(token);
      void queryClient.invalidateQueries({ queryKey: ["profile"] });
      toast("Notifications on — you'll get a ping when follow-ups are due");
    } catch (err) {
      toast(err instanceof Error ? err.message : "Couldn't enable notifications", "err");
    } finally {
      setBusy(false);
    }
  };

  return (
    <div className="mb-4 flex flex-wrap items-center gap-3 rounded-xl border border-accent/20 bg-accent/5 px-4 py-3">
      <BellRing size={15} className="shrink-0 text-accent" />
      <p className="min-w-0 flex-1 text-[13px] text-ink-2">
        Get a browser ping the moment follow-ups come due — the scan runs hourly even when you're not here.
      </p>
      <Button variant="primary" className="!px-3 !py-1.5" disabled={busy} onClick={() => void enable()}>
        {busy ? <Spinner className="border-on-accent/30 border-t-on-accent" /> : null} Enable
      </Button>
      <button
        onClick={() => {
          setDismissed(true);
          try {
            localStorage.setItem("offerloop:push-prompt-dismissed", "1");
          } catch {
            /* private mode */
          }
        }}
        className="cursor-pointer text-xs text-ink-3 hover:text-ink-2"
      >
        Not now
      </button>
    </div>
  );
}

export function DataCard() {
  const { signOut } = useAuth();
  const toast = useToast();
  const [confirmText, setConfirmText] = useState("");
  const [confirming, setConfirming] = useState(false);

  const download = useMutation({
    mutationFn: (name: "applications" | "drafts") => api.account.download(name),
    onError: (err) => toast(err.message, "err"),
  });

  const nuke = useMutation({
    mutationFn: api.account.deleteEverything,
    onSuccess: () => {
      toast("Account data deleted", "info");
      void signOut();
    },
    onError: (err) => toast(err.message, "err"),
  });

  return (
    <section className="ring-card mt-5 rounded-2xl bg-card p-6">
      <div className="flex items-center gap-2">
        <FileDown size={15} className="text-accent" />
        <h2 className="font-display text-sm font-bold tracking-wide">Your data</h2>
      </div>
      <p className="mt-3 text-[13px] text-ink-2">
        Everything you put in leaves with you — flat CSVs, no lock-in.
      </p>
      <div className="mt-3 flex flex-wrap gap-2">
        <Button variant="outline" onClick={() => download.mutate("applications")} disabled={download.isPending}>
          <Download size={14} /> Applications CSV
        </Button>
        <Button variant="outline" onClick={() => download.mutate("drafts")} disabled={download.isPending}>
          <Download size={14} /> Drafts CSV
        </Button>
      </div>

      <div className="mt-5 rounded-xl border border-reject/25 bg-reject/5 p-4">
        <p className="flex items-center gap-1.5 text-[13px] font-semibold text-reject">
          <AlertTriangle size={13} /> Danger zone
        </p>
        {confirming ? (
          <div className="mt-2">
            <p className="text-[13px] text-ink-2">
              This erases every application, draft, nudge and your profile — permanently. Type{" "}
              <strong className="text-ink">DELETE</strong> to confirm.
            </p>
            <div className="mt-2 flex flex-wrap gap-2">
              <input
                className={`${inputClass} max-w-40`}
                value={confirmText}
                onChange={(event) => setConfirmText(event.target.value)}
                placeholder="DELETE"
                aria-label="Type DELETE to confirm"
              />
              <Button
                variant="danger"
                disabled={confirmText !== "DELETE" || nuke.isPending}
                onClick={() => nuke.mutate()}
              >
                {nuke.isPending ? <Spinner /> : null} Erase everything
              </Button>
              <Button onClick={() => setConfirming(false)}>Cancel</Button>
            </div>
          </div>
        ) : (
          <div className="mt-2 flex items-center justify-between gap-3">
            <p className="text-[13px] text-ink-2">Delete your account data and start from zero.</p>
            <Button variant="danger" onClick={() => setConfirming(true)}>
              Delete my data…
            </Button>
          </div>
        )}
      </div>
    </section>
  );
}
