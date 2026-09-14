/** Paste-a-link quick capture: a posting URL (or the whole JD text) in,
 * a prefilled "log application" form out. The single biggest
 * friction-killer between "saw a job" and "it's in the pipeline". */

import { useMutation } from "@tanstack/react-query";
import { Link2, Sparkles } from "lucide-react";
import { useState } from "react";

import { ApiError, api } from "../../api";
import type { CapturedPosting } from "../../types";
import { Spinner } from "../ui";

export function QuickAdd({ onCaptured }: { onCaptured: (posting: CapturedPosting) => void }) {
  const [value, setValue] = useState("");
  const [error, setError] = useState<string | null>(null);

  const capture = useMutation({
    mutationFn: () => {
      const trimmed = value.trim();
      const isUrl = /^https?:\/\/\S+$/i.test(trimmed);
      return api.applications.capture(isUrl ? { url: trimmed } : { text: trimmed });
    },
    onSuccess: (posting) => {
      setValue("");
      setError(null);
      onCaptured(posting);
    },
    onError: (err) => setError(err instanceof ApiError ? err.message : "Capture failed — try again."),
  });

  return (
    <div className="mx-4 mb-3 sm:mx-6" data-tour="quick-add">
      <form
        className="flex items-center gap-2 rounded-xl border border-line bg-card px-3 py-2 transition-colors focus-within:border-accent/50"
        onSubmit={(event) => {
          event.preventDefault();
          if (value.trim() && !capture.isPending) capture.mutate();
        }}
      >
        <Link2 size={15} className="shrink-0 text-ink-3" />
        <input
          className="min-w-0 flex-1 bg-transparent text-base text-ink outline-none placeholder:text-ink-3 sm:text-sm"
          placeholder="Paste a job link or the whole description — Gemini fills in the card"
          value={value}
          onChange={(event) => {
            setValue(event.target.value);
            setError(null);
          }}
        />
        <button
          type="submit"
          disabled={!value.trim() || capture.isPending}
          className="flex shrink-0 cursor-pointer items-center gap-1.5 rounded-lg bg-accent px-3 py-1.5 text-xs font-semibold text-on-accent transition-colors hover:bg-accent-strong disabled:cursor-not-allowed disabled:opacity-45"
        >
          {capture.isPending ? <Spinner className="border-on-accent/30 border-t-on-accent" /> : <Sparkles size={13} />}
          {capture.isPending ? "Reading…" : "Capture"}
        </button>
      </form>
      {error && <p className="mt-1.5 px-1 text-xs text-reject">{error}</p>}
    </div>
  );
}
