import { useMutation, useQueryClient } from "@tanstack/react-query";
import { useState } from "react";

import { api } from "../../api";
import type { CapturedPosting } from "../../types";
import { useToast } from "../Toast";
import { Button, Chip, Field, Modal, inputClass } from "../ui";

export function NewApplicationModal({
  onClose,
  initial,
}: {
  onClose: () => void;
  /** Prefill from paste-a-link capture — user confirms before anything is saved. */
  initial?: CapturedPosting | null;
}) {
  const queryClient = useQueryClient();
  const toast = useToast();
  const [form, setForm] = useState({
    role: initial?.role ?? "",
    company: initial?.company ?? "",
    location: initial?.location ?? "",
    job_type: initial?.job_type || "full-time",
    description: initial?.description ?? "",
    applied_at: new Date().toISOString().slice(0, 10),
  });
  const skills = initial?.skills ?? [];

  const create = useMutation({
    mutationFn: () =>
      api.applications.create({
        ...form,
        skills,
        posting_url: initial?.posting_url ?? "",
        applied_at: new Date(`${form.applied_at}T00:00:00Z`).toISOString(),
      }),
    onSuccess: () => {
      toast("Application logged — +10 momentum, the cadence clock is ticking");
      void queryClient.invalidateQueries({ queryKey: ["applications"] });
      void queryClient.invalidateQueries({ queryKey: ["profile"] });
      onClose();
    },
    onError: (error) => toast(error.message, "err"),
  });

  const set = (key: keyof typeof form) => (event: React.ChangeEvent<HTMLInputElement | HTMLSelectElement | HTMLTextAreaElement>) =>
    setForm((current) => ({ ...current, [key]: event.target.value }));

  return (
    <Modal title={initial ? "Confirm captured job" : "Log an application"} onClose={onClose}>
      <form
        className="space-y-4"
        onSubmit={(event) => {
          event.preventDefault();
          create.mutate();
        }}
      >
        {initial && (
          <p className="rounded-lg border border-accent/20 bg-accent/5 px-3 py-2 text-xs text-ink-2">
            Extracted by Gemini{initial.posting_url ? " from the link you pasted" : " from the pasted description"} —
            check the fields, then log it.
          </p>
        )}
        <Field label="Role *">
          <input
            className={inputClass}
            placeholder="Senior Backend Engineer"
            value={form.role}
            onChange={set("role")}
            autoFocus
            required
          />
        </Field>
        <div className="grid grid-cols-1 gap-3 sm:grid-cols-2">
          <Field label="Company">
            <input className={inputClass} placeholder="Finlo" value={form.company} onChange={set("company")} />
          </Field>
          <Field label="Location">
            <input className={inputClass} placeholder="Bengaluru" value={form.location} onChange={set("location")} />
          </Field>
        </div>
        <div className="grid grid-cols-1 gap-3 sm:grid-cols-2">
          <Field label="Type">
            <select className={inputClass} value={form.job_type} onChange={set("job_type")}>
              <option value="full-time">Full-time</option>
              <option value="contract">Contract</option>
              <option value="internship">Internship</option>
              <option value="part-time">Part-time</option>
            </select>
          </Field>
          <Field label="Applied on">
            <input type="date" className={inputClass} value={form.applied_at} onChange={set("applied_at")} />
          </Field>
        </div>
        {skills.length > 0 && (
          <div className="flex flex-wrap items-center gap-1.5">
            <span className="text-xs text-ink-3">Skills spotted:</span>
            {skills.map((skill) => (
              <Chip key={skill}>{skill}</Chip>
            ))}
          </div>
        )}
        <Field label="Posting description">
          <textarea
            className={`${inputClass} min-h-24 resize-y`}
            placeholder="Paste the job description — Gemini grounds every draft on it."
            value={form.description}
            onChange={set("description")}
          />
        </Field>
        <div className="flex justify-end gap-2 pt-1">
          <Button type="button" onClick={onClose}>
            Cancel
          </Button>
          <Button type="submit" variant="primary" disabled={create.isPending || !form.role.trim()}>
            {create.isPending ? "Logging…" : "Log application"}
          </Button>
        </div>
      </form>
    </Modal>
  );
}
