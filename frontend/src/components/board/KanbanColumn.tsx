import { useDroppable } from "@dnd-kit/core";

import { cn } from "../../lib/format";
import { STATUS_LABEL, type Application, type Status } from "../../types";
import { STATUS_DOT } from "../ui";
import { ApplicationCard } from "./ApplicationCard";

export function KanbanColumn({
  status,
  apps,
  draftCounts,
  onOpen,
}: {
  status: Status;
  apps: Application[];
  draftCounts: Map<string, number>;
  onOpen: (id: string) => void;
}) {
  const { setNodeRef, isOver } = useDroppable({ id: status });

  return (
    <section
      ref={setNodeRef}
      className={cn(
        "flex min-w-0 flex-1 flex-col rounded-2xl border border-transparent bg-panel/60 transition-colors",
        isOver && "border-accent/40 bg-panel",
      )}
    >
      <header className="flex items-center gap-2 px-4 pt-3.5 pb-2">
        <span className={cn("h-2 w-2 rounded-full", STATUS_DOT[status])} />
        <h2 className="font-display text-[13px] font-semibold tracking-wide text-ink">
          {STATUS_LABEL[status]}
        </h2>
        <span className="text-xs text-ink-3">{apps.length}</span>
      </header>

      <div className="flex-1 space-y-2 overflow-y-auto px-3 pb-3">
        {apps.map((app) => (
          <ApplicationCard
            key={app.id}
            app={app}
            draftCount={draftCounts.get(app.id) ?? 0}
            onOpen={() => onOpen(app.id)}
          />
        ))}
        {apps.length === 0 && (
          <div className="rounded-xl border border-dashed border-line-soft px-3 py-8 text-center text-xs text-ink-3">
            {isOver ? "Drop it here" : "Nothing here yet"}
          </div>
        )}
      </div>
    </section>
  );
}
