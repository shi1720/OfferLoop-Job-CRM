import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Save, Sparkles } from "lucide-react";
import { useEffect, useState } from "react";

import { api } from "../api";
import { DataCard, NotificationsCard } from "../components/AccountCards";
import { EngineCard } from "../components/EngineCard";
import { useToast } from "../components/Toast";
import { Button, Field, Spinner, inputClass } from "../components/ui";
import type { Profile } from "../types";

export default function ProfilePage() {
  const queryClient = useQueryClient();
  const toast = useToast();
  const { data: profile, isLoading } = useQuery({ queryKey: ["profile"], queryFn: api.profile.get });

  const [form, setForm] = useState<Partial<Profile> | null>(null);
  // Skills are edited as raw text and parsed only on save — re-parsing on
  // every keystroke ate the spaces in multi-word skills ("product management").
  const [skillsText, setSkillsText] = useState("");
  useEffect(() => {
    if (profile && form === null) {
      setForm({ ...profile });
      setSkillsText(profile.skills.join(", "));
    }
  }, [profile, form]);

  const save = useMutation({
    mutationFn: (payload: Partial<Profile>) =>
      api.profile.update({
        ...payload,
        skills: skillsText
          .split(",")
          .map((skill) => skill.trim())
          .filter(Boolean),
      }),
    onSuccess: () => {
      toast("Profile saved — every future draft uses it");
      void queryClient.invalidateQueries({ queryKey: ["profile"] });
    },
  });

  if (isLoading || !form) {
    return (
      <div className="flex h-full items-center justify-center">
        <Spinner />
      </div>
    );
  }

  const set = <K extends keyof Profile>(key: K, value: Profile[K]) =>
    setForm((current) => ({ ...current, [key]: value }));

  return (
    <div className="animate-rise mx-auto max-w-2xl px-4 py-6 sm:px-6">
      <header className="mb-5">
        <h1 className="font-display text-xl font-bold tracking-tight">Profile & voice</h1>
        <p className="text-[13px] text-ink-2">
          This is the grounding context for every cover letter and follow-up Gemini writes for you — alongside
          your own past drafts, so the words sound like you.
        </p>
      </header>

      <form
        className="ring-card space-y-4 rounded-2xl bg-card p-6"
        onSubmit={(event) => {
          event.preventDefault();
          save.mutate(form);
        }}
      >
        <div className="grid gap-4 sm:grid-cols-2">
          <Field label="Full name">
            <input className={inputClass} value={form.name ?? ""} onChange={(e) => set("name", e.target.value)} />
          </Field>
          <Field label="Years of experience">
            <input
              className={inputClass}
              type="number"
              min={0}
              step={0.5}
              value={form.years_experience ?? 0}
              onChange={(e) => set("years_experience", Number(e.target.value))}
            />
          </Field>
        </div>
        <Field label="Headline">
          <input
            className={inputClass}
            placeholder="Backend engineer — Python, distributed systems"
            value={form.headline ?? ""}
            onChange={(e) => set("headline", e.target.value)}
          />
        </Field>
        <Field label="Skills (comma separated)">
          <input
            className={inputClass}
            placeholder="Product Management, Python, FastAPI, GCP"
            value={skillsText}
            onChange={(e) => setSkillsText(e.target.value)}
          />
        </Field>
        <Field label="Proof points — achievements with numbers">
          <textarea
            className={`${inputClass} min-h-24 resize-y`}
            placeholder="Cut p95 latency 40%; led a 3-engineer pod shipping a service that processes 2M events/day"
            value={form.achievements ?? ""}
            onChange={(e) => set("achievements", e.target.value)}
          />
        </Field>
        <Field label="Preferred tone">
          <input className={inputClass} value={form.tone ?? ""} onChange={(e) => set("tone", e.target.value)} />
        </Field>
        <Field label="Writing rules — hard constraints applied to every draft">
          <textarea
            className={`${inputClass} min-h-20 resize-y`}
            placeholder={"One per line, e.g.\nNever use em dashes.\nKeep cover letters under 180 words.\nBritish spelling."}
            value={form.style_rules ?? ""}
            onChange={(e) => set("style_rules", e.target.value)}
          />
        </Field>

        <div className="flex flex-col gap-3 pt-2 sm:flex-row sm:items-center sm:justify-between">
          <p className="flex items-center gap-1.5 text-[11px] text-ink-3">
            <Sparkles size={12} className="text-accent" />
            Facts only — Gemini is instructed never to invent achievements.
          </p>
          <Button type="submit" variant="primary" disabled={save.isPending} className="w-full sm:w-auto">
            {save.isPending ? <Spinner className="border-on-accent/30 border-t-on-accent" /> : <Save size={15} />}
            Save profile
          </Button>
        </div>
      </form>

      <EngineCard />
      <NotificationsCard />
      <DataCard />
    </div>
  );
}
