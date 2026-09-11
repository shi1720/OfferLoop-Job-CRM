import { useMutation, useQueryClient } from "@tanstack/react-query";
import { useState } from "react";

import { api } from "../../api";
import { useToast } from "../Toast";
import { Button, Field, Modal, inputClass } from "../ui";

export function NewApplicationModal({ onClose }: { onClose: () => void }) {
  const queryClient = useQueryClient();
  const toast = useToast();
  const [form, setForm] = useState({
    role: "",
    company: "",
    location: "",
    job_type: "full-time",
    description: "",
    applied_at: new Date().toISOString().slice(0, 10),
  });

  const create = useMutation({
    mutationFn: () =>
      api.applications.create({
        ...form,
        applied_at: new Date(`${form.applied_at}T00:00:00Z`).toISOString(),
      }),
    onSuccess: () => {
      toast("Application logged — the cadence clock is ticking");
      void queryClient.invalidateQueries({ queryKey: ["applications"] });
      onClose();
    },
    onError: (error) => toast(error.message, "err"),
  });

  const set = (key: keyof typeof form) => (event: React.ChangeEvent<HTMLInputElement | HTMLSelectElement | HTMLTextAreaElement>) =>
    setForm((current) => ({ ...current, [key]: event.target.value }));

  return (
    <Modal title="Log an application" onClose={onClose}>
      <form
        className="space-y-4"
        onSubmit={(event) => {
          event.preventDefault();
          create.mutate();
        }}
      >
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
        <div className="grid grid-cols-2 gap-3">
          <Field label="Company">
            <input className={inputClass} placeholder="Finlo" value={form.company} onChange={set("company")} />
          </Field>
          <Field label="Location">
            <input className={inputClass} placeholder="Bengaluru" value={form.location} onChange={set("location")} />
          </Field>
        </div>
        <div className="grid grid-cols-2 gap-3">
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
