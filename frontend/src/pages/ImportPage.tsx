import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { CheckCircle2, Database, FileSpreadsheet, FileUp, Link2, Sparkles, Unlink, XCircle } from "lucide-react";
import { useRef, useState } from "react";

import { api } from "../api";
import { useToast } from "../components/Toast";
import { Button, Chip, Spinner } from "../components/ui";
import { cn, timeAgo } from "../lib/format";
import type { FileReport, ImportReport } from "../types";

export default function ImportPage() {
  const queryClient = useQueryClient();
  const toast = useToast();
  const [postings, setPostings] = useState<File | null>(null);
  const [drafts, setDrafts] = useState<File | null>(null);
  const [report, setReport] = useState<ImportReport | null>(null);

  const { data: history } = useQuery({ queryKey: ["import-history"], queryFn: api.importHistory });

  const runImport = useMutation({
    mutationFn: (files: { postings?: File; drafts?: File }) => api.importCsvs(files),
    onSuccess: (result) => {
      setReport(result);
      toast(
        `Imported ${result.postings.accepted + result.postings.updated} postings and ${result.drafts.accepted + result.drafts.updated} drafts in ${result.duration_ms} ms`,
      );
      void queryClient.invalidateQueries();
    },
    onError: (error) => toast(error.message, "err"),
  });

  const loadSamples = useMutation({
    mutationFn: async () => {
      const [samplePostings, sampleDrafts] = await Promise.all([
        api.sampleFile("postings"),
        api.sampleFile("drafts"),
      ]);
      setPostings(samplePostings);
      setDrafts(sampleDrafts);
    },
    onSuccess: () => toast("Sample datasets loaded — hit Run import", "info"),
  });

  const canImport = Boolean(postings || drafts) && !runImport.isPending;

  return (
    <div className="animate-rise mx-auto max-w-3xl px-6 py-6">
      <header className="mb-5">
        <h1 className="font-display text-xl font-bold tracking-tight">Bulk import</h1>
        <p className="text-[13px] text-ink-2">
          Drop the evaluation datasets — postings and their historical drafts — and OfferLoop links, indexes,
          and learns from them.
        </p>
      </header>

      <div className="grid gap-3 sm:grid-cols-2">
        <DropZone
          title="Job postings"
          schema="id, from, to, type, description"
          file={postings}
          onFile={setPostings}
        />
        <DropZone
          title="Cover letters & emails"
          schema="id, jobId, type, contents, status"
          file={drafts}
          onFile={setDrafts}
        />
      </div>

      <div className="mt-4 flex items-center gap-2">
        <Button
          variant="primary"
          disabled={!canImport}
          onClick={() => runImport.mutate({ postings: postings ?? undefined, drafts: drafts ?? undefined })}
        >
          {runImport.isPending ? <Spinner className="border-on-accent/30 border-t-on-accent" /> : <FileUp size={15} />}
          Run import
        </Button>
        <Button variant="outline" onClick={() => loadSamples.mutate()} disabled={loadSamples.isPending}>
          {loadSamples.isPending ? <Spinner /> : <Database size={14} />}
          Load sample datasets
        </Button>
        <p className="ml-auto hidden text-[11px] text-ink-3 sm:block">
          Re-imports are idempotent — same ids update, never duplicate.
        </p>
      </div>

      {report && <ReportPanel report={report} />}

      {(history?.length ?? 0) > 0 && (
        <section className="mt-8">
          <h2 className="font-display mb-3 text-sm font-semibold tracking-wide">Recent imports</h2>
          <ul className="space-y-2">
            {history!.map((entry) => (
              <li
                key={entry.id}
                className="flex items-center gap-3 rounded-xl border border-line-soft bg-card px-4 py-2.5 text-sm"
              >
                <FileSpreadsheet size={15} className="text-ink-3" />
                <span className="text-ink-2">
                  {entry.postings.accepted + entry.postings.updated} postings ·{" "}
                  {entry.drafts.accepted + entry.drafts.updated} drafts · {entry.linked_drafts} linked
                </span>
                <span className="ml-auto text-[11px] text-ink-3">
                  {entry.duration_ms} ms · {timeAgo(entry.created_at)}
                </span>
              </li>
            ))}
          </ul>
        </section>
      )}
    </div>
  );
}

function DropZone({
  title,
  schema,
  file,
  onFile,
}: {
  title: string;
  schema: string;
  file: File | null;
  onFile: (file: File | null) => void;
}) {
  const inputRef = useRef<HTMLInputElement>(null);
  const [over, setOver] = useState(false);

  return (
    <div
      onClick={() => inputRef.current?.click()}
      onDragOver={(event) => {
        event.preventDefault();
        setOver(true);
      }}
      onDragLeave={() => setOver(false)}
      onDrop={(event) => {
        event.preventDefault();
        setOver(false);
        const dropped = event.dataTransfer.files[0];
        if (dropped) onFile(dropped);
      }}
      className={cn(
        "cursor-pointer rounded-2xl border-2 border-dashed p-5 transition-all",
        over
          ? "border-accent bg-accent/5"
          : file
            ? "border-offer/40 bg-card"
            : "border-line bg-card hover:border-ink-3",
      )}
    >
      <input
        ref={inputRef}
        type="file"
        accept=".csv,text/csv"
        className="hidden"
        onChange={(event) => onFile(event.target.files?.[0] ?? null)}
      />
      <div className="flex items-center gap-2">
        {file ? <CheckCircle2 size={16} className="text-offer" /> : <FileUp size={16} className="text-ink-3" />}
        <p className="text-sm font-semibold text-ink">{title}</p>
      </div>
      {file ? (
        <p className="mt-2 truncate text-xs text-ink-2">
          {file.name} · {(file.size / 1024).toFixed(1)} KB
        </p>
      ) : (
        <p className="mt-2 text-xs text-ink-3">Drop a CSV or click to browse</p>
      )}
      <p className="mt-3 rounded-lg bg-panel px-2.5 py-1.5 font-mono text-[11px] text-ink-3">{schema}</p>
    </div>
  );
}

function ReportPanel({ report }: { report: ImportReport }) {
  return (
    <section className="ring-card animate-rise mt-6 rounded-2xl bg-card p-5">
      <div className="flex items-center justify-between">
        <h2 className="font-display text-sm font-semibold tracking-wide">Import report</h2>
        <Chip>{report.duration_ms} ms end-to-end</Chip>
      </div>

      <div className="mt-4 grid grid-cols-2 gap-3 sm:grid-cols-4">
        <ReportStat label="Postings in" value={report.postings.accepted + report.postings.updated} />
        <ReportStat label="Drafts in" value={report.drafts.accepted + report.drafts.updated} />
        <ReportStat
          label="Linked by jobId"
          value={report.linked_drafts}
          icon={<Link2 size={12} className="text-offer" />}
        />
        <ReportStat
          label="Orphans kept"
          value={report.orphaned_drafts}
          icon={<Unlink size={12} className="text-interview" />}
        />
      </div>

      {report.relinked_drafts > 0 && (
        <p className="mt-3 flex items-center gap-1.5 text-xs text-ink-2">
          <Link2 size={12} className="text-offer" />
          {report.relinked_drafts} previously orphaned draft{report.relinked_drafts > 1 ? "s" : ""} adopted by
          newly imported postings.
        </p>
      )}
      {report.embedded > 0 && (
        <p className="mt-3 flex items-center gap-1.5 text-xs text-ink-2">
          <Sparkles size={12} className="text-accent" />
          {report.embedded} drafts embedded with Gemini for semantic voice retrieval.
        </p>
      )}

      <RejectedRows title="postings" fileReport={report.postings} />
      <RejectedRows title="drafts" fileReport={report.drafts} />
    </section>
  );
}

function ReportStat({ label, value, icon }: { label: string; value: number; icon?: React.ReactNode }) {
  return (
    <div className="rounded-xl bg-panel p-3">
      <p className="flex items-center gap-1 text-[11px] tracking-wide text-ink-3 uppercase">
        {icon} {label}
      </p>
      <p className="font-display mt-1 text-xl font-bold">{value}</p>
    </div>
  );
}

function RejectedRows({ title, fileReport }: { title: string; fileReport: FileReport }) {
  if (fileReport.rejected.length === 0) return null;
  return (
    <div className="mt-4">
      <p className="flex items-center gap-1.5 text-xs font-medium text-reject">
        <XCircle size={13} />
        {fileReport.rejected.length} {title} row{fileReport.rejected.length > 1 ? "s" : ""} rejected (everything
        else imported)
      </p>
      <ul className="mt-2 space-y-1">
        {fileReport.rejected.map((row) => (
          <li key={`${row.row}-${row.reason}`} className="rounded-lg bg-panel px-3 py-1.5 font-mono text-[11px] text-ink-2">
            row {row.row}: {row.reason}
          </li>
        ))}
      </ul>
    </div>
  );
}
