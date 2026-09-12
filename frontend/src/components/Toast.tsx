/** Minimal toast system: push a message, it slides in bottom-right.
 * A toast can carry one action ("Undo") — clicking it runs the callback
 * and dismisses the toast. */

import { createContext, useCallback, useContext, useRef, useState } from "react";

import { cn } from "../lib/format";

type Tone = "ok" | "err" | "info";

interface ToastAction {
  label: string;
  onClick: () => void;
}

interface Toast {
  id: number;
  message: string;
  tone: Tone;
  action?: ToastAction;
}

type PushToast = (message: string, tone?: Tone, action?: ToastAction) => void;

const ToastContext = createContext<PushToast>(() => {});

export function ToastProvider({ children }: { children: React.ReactNode }) {
  const [toasts, setToasts] = useState<Toast[]>([]);
  const nextId = useRef(1);

  const push = useCallback<PushToast>((message, tone = "ok", action) => {
    const id = nextId.current++;
    setToasts((current) => [...current, { id, message, tone, action }]);
    // action toasts stay longer — an Undo needs time to be seen
    window.setTimeout(
      () => setToasts((current) => current.filter((t) => t.id !== id)),
      action ? 7000 : 4200,
    );
  }, []);

  const dismiss = (id: number) => setToasts((current) => current.filter((t) => t.id !== id));

  return (
    <ToastContext.Provider value={push}>
      {children}
      <div className="pointer-events-none fixed right-4 bottom-4 left-4 z-[70] flex flex-col items-end gap-2 sm:left-auto">
        {toasts.map((toast) => (
          <div
            key={toast.id}
            role="status"
            className={cn(
              "animate-rise pointer-events-auto flex max-w-sm items-center gap-3 rounded-xl border px-4 py-3 text-sm shadow-2xl backdrop-blur",
              toast.tone === "ok" && "border-offer/30 bg-card text-ink",
              toast.tone === "err" && "border-reject/40 bg-card text-ink",
              toast.tone === "info" && "border-line bg-card text-ink",
            )}
          >
            <span
              className={cn(
                "inline-block h-2 w-2 shrink-0 rounded-full",
                toast.tone === "ok" && "bg-offer",
                toast.tone === "err" && "bg-reject",
                toast.tone === "info" && "bg-applied",
              )}
            />
            <span className="min-w-0">{toast.message}</span>
            {toast.action && (
              <button
                onClick={() => {
                  toast.action?.onClick();
                  dismiss(toast.id);
                }}
                className="ml-1 shrink-0 cursor-pointer rounded-lg border border-accent/40 px-2.5 py-1 text-xs font-semibold text-accent transition-colors hover:bg-accent/10"
              >
                {toast.action.label}
              </button>
            )}
          </div>
        ))}
      </div>
    </ToastContext.Provider>
  );
}

export function useToast() {
  return useContext(ToastContext);
}
