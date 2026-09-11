import { ArrowRight, BellRing, FileUp, PenLine, TrendingUp, TriangleAlert } from "lucide-react";
import { useState } from "react";

import { useAuth } from "../auth";
import { LogoMark } from "../components/Logo";
import { Spinner } from "../components/ui";

const AUTH_ERROR_HINTS: Record<string, string> = {
  "auth/unauthorized-domain":
    "This domain isn't on the Firebase authorized list. Add this site's exact host under Authentication → Settings → Authorized domains.",
  "auth/operation-not-allowed":
    "Google sign-in is disabled for this Firebase project. Enable it under Authentication → Sign-in method.",
  "auth/popup-blocked": "Your browser blocked the sign-in popup — allow popups for this site and retry.",
  "auth/popup-closed-by-user": "The popup closed before sign-in finished. Try again.",
  "auth/configuration-not-found":
    "Firebase Authentication isn't initialized for this project yet (click Get started in the Firebase console).",
};

const FEATURES = [
  { icon: TrendingUp, text: "A kanban pipeline that treats your search like a sales funnel" },
  { icon: PenLine, text: "Cover letters & follow-ups written by Gemini, in your own voice" },
  { icon: BellRing, text: "Scheduled nudges so no application goes quiet again" },
  { icon: FileUp, text: "Bulk-import postings & drafts from CSV in seconds" },
];

export default function LoginPage() {
  const { config, signIn } = useAuth();
  const [busy, setBusy] = useState(false);
  const [authError, setAuthError] = useState<string | null>(null);

  const handleSignIn = async () => {
    setBusy(true);
    setAuthError(null);
    try {
      await signIn();
    } catch (err) {
      const code = (err as { code?: string; message?: string })?.code ?? "";
      const message = (err as { message?: string })?.message ?? "Sign-in failed";
      setAuthError(AUTH_ERROR_HINTS[code] ?? `${code || "Sign-in failed"} — ${message}`);
    } finally {
      setBusy(false);
    }
  };

  return (
    <div className="relative flex min-h-screen items-center justify-center overflow-hidden px-6">
      {/* Aurora backdrop */}
      <div className="pointer-events-none absolute inset-0" aria-hidden>
        <div className="animate-drift absolute -top-40 -left-40 h-[34rem] w-[34rem] rounded-full bg-accent/10 blur-[120px]" />
        <div className="animate-drift absolute -right-40 -bottom-52 h-[30rem] w-[30rem] rounded-full bg-applied/10 blur-[120px] [animation-delay:-7s]" />
        <div
          className="absolute inset-0 opacity-[0.35]"
          style={{
            backgroundImage:
              "linear-gradient(var(--color-line-soft) 1px, transparent 1px), linear-gradient(90deg, var(--color-line-soft) 1px, transparent 1px)",
            backgroundSize: "44px 44px",
            maskImage: "radial-gradient(ellipse 70% 60% at 50% 40%, black 30%, transparent 75%)",
          }}
        />
      </div>

      <div className="animate-rise relative grid w-full max-w-4xl gap-12 md:grid-cols-[1.2fr_1fr] md:items-center">
        {/* Pitch */}
        <div>
          <div className="mb-8 flex items-center gap-3">
            <LogoMark size={40} />
            <span className="font-display text-2xl font-bold tracking-tight">
              Offer<span className="text-accent">Loop</span>
            </span>
          </div>

          <h1 className="font-display text-4xl leading-[1.12] font-bold tracking-tight md:text-[2.6rem]">
            Sales teams never forget to follow up.
            <br />
            <span className="text-accent">Now you won't either.</span>
          </h1>

          <p className="mt-5 max-w-md text-[15px] leading-relaxed text-ink-2">
            Three out of four candidates get ghosted after an interview. OfferLoop runs your search
            like a sales pipeline — tracked stages, AI-drafted outreach, perfectly timed follow-ups.
          </p>

          <ul className="mt-8 space-y-3">
            {FEATURES.map(({ icon: Icon, text }) => (
              <li key={text} className="flex items-start gap-3 text-sm text-ink-2">
                <span className="mt-0.5 flex h-6 w-6 shrink-0 items-center justify-center rounded-md border border-line bg-card">
                  <Icon size={13} className="text-accent" />
                </span>
                {text}
              </li>
            ))}
          </ul>
        </div>

        {/* Sign-in card */}
        <div className="ring-card rounded-2xl bg-panel/80 p-7 backdrop-blur">
          <h2 className="font-display text-lg font-semibold">
            {config?.mode === "demo" ? "Step into the demo workspace" : "Welcome back"}
          </h2>
          <p className="mt-1 text-sm text-ink-2">
            {config?.mode === "demo"
              ? "A seeded pipeline: 12 imported postings, 16 historical drafts, live nudges."
              : "Sign in securely with your Google account."}
          </p>

          <button
            onClick={() => void handleSignIn()}
            disabled={busy}
            className="mt-6 flex w-full cursor-pointer items-center justify-center gap-2 rounded-xl bg-accent px-4 py-3 font-display text-sm font-semibold text-on-accent shadow-[0_4px_24px_-8px_var(--color-accent)] transition-all hover:bg-accent-strong disabled:opacity-60"
          >
            {busy ? (
              <Spinner className="border-on-accent/30 border-t-on-accent" />
            ) : (
              <>
                {config?.mode === "demo" ? "Enter OfferLoop" : "Continue with Google"}
                <ArrowRight size={16} />
              </>
            )}
          </button>

          {authError && (
            <p className="mt-3 flex items-start gap-2 rounded-lg border border-reject/30 bg-reject/10 px-3 py-2 text-xs leading-relaxed text-ink-2">
              <TriangleAlert size={14} className="mt-0.5 shrink-0 text-reject" />
              {authError}
            </p>
          )}

          <div className="mt-6 border-t border-line-soft pt-4">
            <p className="text-[11px] leading-relaxed text-ink-3">
              Built end-to-end on Google Cloud — Gemini 3.7 Flash & 3.1 Pro on Vertex AI, Firestore,
              Firebase Auth, Cloud Scheduler, Cloud Run.
            </p>
          </div>
        </div>
      </div>
    </div>
  );
}
