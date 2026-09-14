/** "AI engine" card: shows what powers draft generation for this account
 * and lets the user plug in their own free Gemini API key (BYOK).
 * The raw key is validated live server-side, stored encrypted, and only
 * ever displayed masked from then on. */

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { ExternalLink, KeyRound, ShieldCheck, Trash2 } from "lucide-react";
import { useState } from "react";

import { ApiError, api } from "../api";
import { cn } from "../lib/format";
import { useToast } from "./Toast";
import { Button, Spinner, inputClass } from "./ui";

export function EngineCard() {
  const queryClient = useQueryClient();
  const toast = useToast();
  const { data: profile } = useQuery({ queryKey: ["profile"], queryFn: api.profile.get });

  const [key, setKey] = useState("");
  const [error, setError] = useState<string | null>(null);

  const refresh = () => void queryClient.invalidateQueries({ queryKey: ["profile"] });

  const save = useMutation({
    mutationFn: () => api.profile.setGeminiKey(key),
    onSuccess: () => {
      setKey("");
      setError(null);
      toast("Key verified and saved — drafts now run on your own Gemini quota");
      refresh();
    },
    onError: (err) => setError(err instanceof ApiError ? err.message : "Couldn't save the key — try again."),
  });

  const remove = useMutation({
    mutationFn: api.profile.removeGeminiKey,
    onSuccess: () => {
      toast("Key removed", "info");
      refresh();
    },
  });

  if (!profile) return null;

  const engine = profile.engine;
  const status =
    engine === "demo"
      ? { dot: "bg-applied", text: "Demo workspace — the deterministic template writer. No key needed here." }
      : engine === "your_key"
        ? { dot: "bg-offer", text: `Running on your own Gemini key ${profile.gemini_key_masked ?? ""}` }
        : engine === "free_credits"
          ? {
              dot: "bg-accent",
              text: `Running on OfferLoop's free allowance — ${profile.free_remaining} free AI draft${profile.free_remaining === 1 ? "" : "s"} left`,
            }
          : { dot: "bg-reject", text: "Free allowance used up — add your free Gemini key to keep generating." };

  return (
    <section className="ring-card mt-5 rounded-2xl bg-card p-6" data-tour="engine">
      <div className="flex items-center gap-2">
        <KeyRound size={15} className="text-accent" />
        <h2 className="font-display text-sm font-bold tracking-wide">AI engine</h2>
      </div>

      <p className="mt-3 flex items-center gap-2 text-[13px] text-ink-2">
        <span className={cn("inline-block h-2 w-2 shrink-0 rounded-full", status.dot)} />
        {status.text}
      </p>

      {engine === "your_key" ? (
        <div className="mt-3">
          <Button variant="outline" className="!px-3 !py-1.5" onClick={() => remove.mutate()} disabled={remove.isPending}>
            <Trash2 size={13} /> Remove key
          </Button>
        </div>
      ) : engine !== "demo" ? (
        <form
          className="mt-4"
          onSubmit={(event) => {
            event.preventDefault();
            if (key.trim()) save.mutate();
          }}
        >
          <div className="flex gap-2">
            <input
              className={`${inputClass} min-w-0 flex-1 font-mono`}
              type="password"
              placeholder="Paste your Gemini API key (AIza…)"
              value={key}
              onChange={(event) => {
                setKey(event.target.value);
                setError(null);
              }}
              autoComplete="off"
            />
            <Button type="submit" variant="primary" disabled={save.isPending || !key.trim()}>
              {save.isPending ? <Spinner className="border-on-accent/30 border-t-on-accent" /> : null}
              {save.isPending ? "Verifying…" : "Validate & save"}
            </Button>
          </div>
          {error && <p className="mt-2 text-[13px] text-reject">{error}</p>}
          <p className="mt-2 text-[12px] text-ink-3">
            Free from{" "}
            <a
              href="https://aistudio.google.com/apikey"
              target="_blank"
              rel="noreferrer"
              className="inline-flex items-center gap-0.5 text-accent hover:underline"
            >
              Google AI Studio <ExternalLink size={10} />
            </a>{" "}
            — takes under a minute, no card required.
          </p>
        </form>
      ) : null}

      {engine !== "demo" && (
        <p className="mt-3 flex items-center gap-1.5 text-[11px] text-ink-3">
          <ShieldCheck size={12} className="shrink-0 text-offer" />
          Stored encrypted, never displayed again, and only ever sent to Google's Gemini API to write your drafts.
        </p>
      )}
    </section>
  );
}
