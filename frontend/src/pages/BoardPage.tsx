import {
  DndContext,
  DragOverlay,
  PointerSensor,
  useSensor,
  useSensors,
  type DragEndEvent,
  type DragStartEvent,
} from "@dnd-kit/core";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Plus, RadarIcon } from "lucide-react";
import { useMemo, useState } from "react";
import { useSearchParams } from "react-router-dom";

import { api } from "../api";
import { ApplicationCard } from "../components/board/ApplicationCard";
import { ApplicationDrawer } from "../components/board/ApplicationDrawer";
import { NewApplicationModal } from "../components/board/NewApplicationModal";
import { KanbanColumn } from "../components/board/KanbanColumn";
import { useToast } from "../components/Toast";
import { Button, Spinner } from "../components/ui";
import { STATUSES, STATUS_LABEL, type Application, type Status } from "../types";

export default function BoardPage() {
  const queryClient = useQueryClient();
  const toast = useToast();
  const [searchParams, setSearchParams] = useSearchParams();
  const [creating, setCreating] = useState(false);
  const [dragged, setDragged] = useState<Application | null>(null);
  const selectedId = searchParams.get("app");

  const { data: apps, isLoading } = useQuery({ queryKey: ["applications"], queryFn: api.applications.list });
  const { data: drafts } = useQuery({ queryKey: ["drafts"], queryFn: () => api.drafts.list() });

  const draftCounts = useMemo(() => {
    const counts = new Map<string, number>();
    for (const draft of drafts ?? []) {
      counts.set(draft.application_id, (counts.get(draft.application_id) ?? 0) + 1);
    }
    return counts;
  }, [drafts]);

  const byStatus = useMemo(() => {
    const groups: Record<Status, Application[]> = { applied: [], interview: [], offer: [], reject: [] };
    for (const app of apps ?? []) groups[app.status].push(app);
    return groups;
  }, [apps]);

  const move = useMutation({
    mutationFn: ({ id, status }: { id: string; status: Status }) => api.applications.setStatus(id, status),
    onMutate: async ({ id, status }) => {
      await queryClient.cancelQueries({ queryKey: ["applications"] });
      const previous = queryClient.getQueryData<Application[]>(["applications"]);
      queryClient.setQueryData<Application[]>(["applications"], (current) =>
        current?.map((app) => (app.id === id ? { ...app, status } : app)),
      );
      return { previous };
    },
    onError: (_err, _vars, context) => {
      queryClient.setQueryData(["applications"], context?.previous);
      toast("Couldn't move the application — try again", "err");
    },
    onSuccess: (updated) => {
      toast(`Moved to ${STATUS_LABEL[updated.status]}`);
      void queryClient.invalidateQueries({ queryKey: ["applications"] });
      void queryClient.invalidateQueries({ queryKey: ["nudges"] });
    },
  });

  const scan = useMutation({
    mutationFn: api.scan,
    onSuccess: (report) => {
      toast(
        report.nudges_created > 0
          ? `Scan done: ${report.nudges_created} nudge${report.nudges_created > 1 ? "s" : ""}, ${report.drafts_generated} draft${report.drafts_generated === 1 ? "" : "s"} auto-written`
          : "Scan done — pipeline is fully worked",
        "info",
      );
      void queryClient.invalidateQueries({ queryKey: ["nudges"] });
      void queryClient.invalidateQueries({ queryKey: ["drafts"] });
    },
  });

  const sensors = useSensors(useSensor(PointerSensor, { activationConstraint: { distance: 6 } }));

  const onDragStart = (event: DragStartEvent) => {
    setDragged(apps?.find((app) => app.id === event.active.id) ?? null);
  };

  const onDragEnd = (event: DragEndEvent) => {
    setDragged(null);
    const target = event.over?.id as Status | undefined;
    const app = apps?.find((a) => a.id === event.active.id);
    if (target && app && app.status !== target) move.mutate({ id: app.id, status: target });
  };

  const openDrawer = (id: string) => setSearchParams({ app: id });
  const closeDrawer = () => setSearchParams({});

  return (
    <div className="flex h-full flex-col">
      <header className="flex items-center justify-between px-6 pt-5 pb-4">
        <div>
          <h1 className="font-display text-xl font-bold tracking-tight">Pipeline</h1>
          <p className="text-[13px] text-ink-2">
            {apps?.length ?? 0} applications · drag a card to change its stage
          </p>
        </div>
        <div className="flex items-center gap-2">
          <Button variant="outline" onClick={() => scan.mutate()} disabled={scan.isPending}>
            {scan.isPending ? <Spinner /> : <RadarIcon size={15} />}
            Scan my pipeline
          </Button>
          <Button variant="primary" onClick={() => setCreating(true)}>
            <Plus size={15} /> Log application
          </Button>
        </div>
      </header>

      {isLoading ? (
        <div className="flex flex-1 items-center justify-center">
          <Spinner />
        </div>
      ) : (
        <DndContext sensors={sensors} onDragStart={onDragStart} onDragEnd={onDragEnd}>
          <div className="animate-rise flex flex-1 gap-3 overflow-x-auto px-6 pb-6">
            {STATUSES.map((status) => (
              <KanbanColumn
                key={status}
                status={status}
                apps={byStatus[status]}
                draftCounts={draftCounts}
                onOpen={openDrawer}
              />
            ))}
          </div>
          <DragOverlay dropAnimation={null}>
            {dragged && <ApplicationCard app={dragged} draftCount={draftCounts.get(dragged.id) ?? 0} overlay />}
          </DragOverlay>
        </DndContext>
      )}

      {creating && <NewApplicationModal onClose={() => setCreating(false)} />}
      {selectedId && <ApplicationDrawer applicationId={selectedId} onClose={closeDrawer} />}
    </div>
  );
}
