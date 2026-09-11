import { useDraggable } from "@dnd-kit/core";
import { Clock, FileText, Ghost } from "lucide-react";

import { cn, daysSince, initials, stalenessTone } from "../../lib/format";
import type { Application } from "../../types";

const TONE_STYLES = {
  fresh: "text-ink-3",
  warm: "text-interview",
  hot: "text-reject",
} as const;

export function ApplicationCard({
  app,
  draftCount,
  onOpen,
  overlay,
}: {
  app: Application;
  draftCount: number;
  onOpen?: () => void;
  overlay?: boolean;
}) {
  const { attributes, listeners, setNodeRef, transform, isDragging } = useDraggable({
    id: app.id,
    disabled: overlay,
  });

  const quiet = daysSince(app.last_activity_at);
  const tone = stalenessTone(quiet);
  const isOpenStage = app.status === "applied" || app.status === "interview";

  return (
    <div
      ref={setNodeRef}
      {...listeners}
      {...attributes}
      onClick={onOpen}
      style={transform ? { transform: `translate(${transform.x}px, ${transform.y}px)` } : undefined}
      className={cn(
        "group cursor-pointer rounded-xl border border-line-soft bg-card p-3.5 transition-all duration-150",
        "hover:border-line hover:bg-raised/70",
        isDragging && "z-30 opacity-40",
        overlay && "ring-card rotate-2 border-accent/40 bg-raised shadow-2xl",
      )}
    >
      <div className="flex items-start gap-3">
        <span className="flex h-9 w-9 shrink-0 items-center justify-center rounded-lg bg-raised font-display text-xs font-bold text-ink-2 group-hover:text-accent">
          {initials(app.company || app.role)}
        </span>
        <div className="min-w-0 flex-1">
          <p className="line-clamp-2 text-sm leading-tight font-semibold text-ink">{app.role}</p>
          <p className="mt-0.5 truncate text-xs text-ink-2">
            {app.company || <span className="italic">Confidential</span>}
            {app.location && <span className="text-ink-3"> · {app.location}</span>}
          </p>
        </div>
      </div>

      <div className="mt-3 flex items-center gap-3 text-[11px] text-ink-3">
        <span className={cn("inline-flex items-center gap-1", isOpenStage && TONE_STYLES[tone])}>
          {isOpenStage && tone === "hot" ? <Ghost size={11} /> : <Clock size={11} />}
          {isOpenStage
            ? quiet === 0
              ? "active today"
              : `${quiet}d quiet`
            : `updated ${quiet === 0 ? "today" : `${quiet}d ago`}`}
        </span>
        {draftCount > 0 && (
          <span className="inline-flex items-center gap-1">
            <FileText size={11} />
            {draftCount} draft{draftCount > 1 ? "s" : ""}
          </span>
        )}
        {app.source === "import" && <span className="ml-auto rounded bg-raised px-1.5 py-0.5">CSV</span>}
      </div>
    </div>
  );
}
