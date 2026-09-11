/** Shared primitives: buttons, badges, empty states, modal, spinner. */

import { X } from "lucide-react";
import { useEffect } from "react";

import { cn } from "../lib/format";
import { STATUS_LABEL, type Status } from "../types";

export function Button({
  variant = "ghost",
  className,
  ...props
}: React.ButtonHTMLAttributes<HTMLButtonElement> & { variant?: "primary" | "ghost" | "outline" | "danger" }) {
  return (
    <button
      className={cn(
        "inline-flex cursor-pointer items-center justify-center gap-1.5 rounded-lg text-sm font-medium transition-all duration-150 focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-accent disabled:cursor-not-allowed disabled:opacity-45",
        "px-3.5 py-2",
        variant === "primary" &&
          "bg-accent text-on-accent shadow-[0_2px_12px_-4px_var(--color-accent)] hover:bg-accent-strong",
        variant === "ghost" && "text-ink-2 hover:bg-raised hover:text-ink",
        variant === "outline" && "border border-line text-ink hover:border-ink-3 hover:bg-raised",
        variant === "danger" && "text-reject hover:bg-reject/10",
        className,
      )}
      {...props}
    />
  );
}

const STATUS_STYLES: Record<Status, string> = {
  applied: "text-applied bg-applied/10 border-applied/25",
  interview: "text-interview bg-interview/10 border-interview/25",
  offer: "text-offer bg-offer/10 border-offer/25",
  reject: "text-reject bg-reject/10 border-reject/25",
};

export const STATUS_DOT: Record<Status, string> = {
  applied: "bg-applied",
  interview: "bg-interview",
  offer: "bg-offer",
  reject: "bg-reject",
};

export function StatusBadge({ status, className }: { status: Status; className?: string }) {
  return (
    <span
      className={cn(
        "inline-flex items-center gap-1.5 rounded-full border px-2.5 py-0.5 text-xs font-medium",
        STATUS_STYLES[status],
        className,
      )}
    >
      <span className={cn("h-1.5 w-1.5 rounded-full", STATUS_DOT[status])} />
      {STATUS_LABEL[status]}
    </span>
  );
}

export function Chip({ children, className }: { children: React.ReactNode; className?: string }) {
  return (
    <span
      className={cn(
        "inline-flex items-center gap-1 rounded-md border border-line bg-raised/60 px-2 py-0.5 text-xs text-ink-2",
        className,
      )}
    >
      {children}
    </span>
  );
}

export function Spinner({ className }: { className?: string }) {
  return (
    <span
      className={cn(
        "inline-block h-4 w-4 animate-spin rounded-full border-2 border-line border-t-accent",
        className,
      )}
      aria-label="Loading"
    />
  );
}

export function EmptyState({
  icon,
  title,
  hint,
  action,
}: {
  icon: React.ReactNode;
  title: string;
  hint?: string;
  action?: React.ReactNode;
}) {
  return (
    <div className="flex flex-col items-center justify-center gap-2 rounded-2xl border border-dashed border-line px-6 py-14 text-center">
      <div className="text-ink-3">{icon}</div>
      <p className="font-display text-base font-semibold text-ink">{title}</p>
      {hint && <p className="max-w-sm text-sm text-ink-2">{hint}</p>}
      {action && <div className="mt-3">{action}</div>}
    </div>
  );
}

export function Modal({
  title,
  onClose,
  children,
  wide,
}: {
  title: string;
  onClose: () => void;
  children: React.ReactNode;
  wide?: boolean;
}) {
  useEffect(() => {
    const onKey = (event: KeyboardEvent) => event.key === "Escape" && onClose();
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [onClose]);

  return (
    <div className="fixed inset-0 z-[60] flex items-center justify-center p-4">
      <div className="absolute inset-0 bg-page/70 backdrop-blur-sm" onClick={onClose} />
      <div
        role="dialog"
        aria-label={title}
        className={cn(
          "ring-card animate-rise relative max-h-[88vh] w-full overflow-y-auto rounded-2xl bg-panel p-6",
          wide ? "max-w-2xl" : "max-w-md",
        )}
      >
        <div className="mb-4 flex items-center justify-between">
          <h2 className="font-display text-lg font-semibold">{title}</h2>
          <Button onClick={onClose} aria-label="Close" className="!p-1.5">
            <X size={16} />
          </Button>
        </div>
        {children}
      </div>
    </div>
  );
}

export const inputClass =
  "w-full rounded-lg border border-line bg-card px-3 py-2 text-sm text-ink placeholder:text-ink-3 focus:border-accent/60 focus:outline-none transition-colors";

export function Field({ label, children }: { label: string; children: React.ReactNode }) {
  return (
    <label className="block">
      <span className="mb-1.5 block text-xs font-medium tracking-wide text-ink-2 uppercase">{label}</span>
      {children}
    </label>
  );
}
