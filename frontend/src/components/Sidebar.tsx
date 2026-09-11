import { useQuery } from "@tanstack/react-query";
import { BarChart3, BellRing, FileUp, Kanban, LogOut, UserRound } from "lucide-react";
import { NavLink } from "react-router-dom";

import { api } from "../api";
import { useAuth } from "../auth";
import { cn, initials } from "../lib/format";
import { Wordmark } from "./Logo";

const NAV = [
  { to: "/", label: "Pipeline", icon: Kanban },
  { to: "/nudges", label: "Nudges", icon: BellRing },
  { to: "/import", label: "Import", icon: FileUp },
  { to: "/analytics", label: "Analytics", icon: BarChart3 },
];

export function Sidebar() {
  const { user, config, signOut } = useAuth();
  const { data: nudges } = useQuery({
    queryKey: ["nudges", "pending"],
    queryFn: () => api.nudges.list("pending"),
    refetchInterval: 60_000,
  });
  const pending = nudges?.length ?? 0;

  return (
    <aside className="flex w-60 shrink-0 flex-col border-r border-line-soft bg-panel">
      <div className="px-5 pt-5 pb-4">
        <Wordmark />
        <p className="mt-1 pl-[38px] text-[11px] leading-tight text-ink-3">a sales CRM for your job search</p>
      </div>

      <nav className="flex-1 space-y-1 px-3">
        {NAV.map(({ to, label, icon: Icon }) => (
          <NavLink
            key={to}
            to={to}
            end={to === "/"}
            className={({ isActive }) =>
              cn(
                "group flex items-center gap-3 rounded-lg px-3 py-2 text-sm font-medium transition-colors",
                isActive ? "bg-raised text-ink" : "text-ink-2 hover:bg-raised/60 hover:text-ink",
              )
            }
          >
            {({ isActive }) => (
              <>
                <Icon size={17} className={cn(isActive ? "text-accent" : "text-ink-3 group-hover:text-ink-2")} />
                {label}
                {label === "Nudges" && pending > 0 && (
                  <span className="ml-auto rounded-full bg-accent px-1.5 py-0.5 text-[10px] leading-none font-bold text-on-accent">
                    {pending}
                  </span>
                )}
              </>
            )}
          </NavLink>
        ))}
      </nav>

      {config?.mode === "demo" && (
        <div className="mx-3 mb-3 rounded-lg border border-accent/20 bg-accent/5 px-3 py-2">
          <p className="text-[11px] leading-snug text-ink-2">
            <span className="font-semibold text-accent">Demo workspace</span> — seeded through the same CSV
            pipeline the evaluators test.
          </p>
        </div>
      )}

      <div className="border-t border-line-soft p-3">
        <NavLink
          to="/profile"
          className={({ isActive }) =>
            cn(
              "flex items-center gap-3 rounded-lg px-2 py-2 transition-colors",
              isActive ? "bg-raised" : "hover:bg-raised/60",
            )
          }
        >
          <span className="flex h-8 w-8 items-center justify-center rounded-full bg-raised font-display text-xs font-bold text-accent">
            {user?.photo ? (
              <img src={user.photo} alt="" className="h-8 w-8 rounded-full" />
            ) : (
              initials(user?.name ?? "?")
            )}
          </span>
          <span className="min-w-0 flex-1">
            <span className="block truncate text-sm font-medium text-ink">{user?.name}</span>
            <span className="flex items-center gap-1 text-[11px] text-ink-3">
              <UserRound size={10} /> Profile & voice
            </span>
          </span>
          <button
            onClick={(event) => {
              event.preventDefault();
              void signOut();
            }}
            aria-label="Sign out"
            className="cursor-pointer rounded-md p-1.5 text-ink-3 transition-colors hover:bg-overlay hover:text-ink"
          >
            <LogOut size={14} />
          </button>
        </NavLink>
      </div>
    </aside>
  );
}
