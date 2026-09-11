/** Minimal toast system: push a message, it slides in bottom-right. */

import { createContext, useCallback, useContext, useRef, useState } from "react";

import { cn } from "../lib/format";

type Tone = "ok" | "err" | "info";

interface Toast {
  id: number;
  message: string;
  tone: Tone;
}

const ToastContext = createContext<(message: string, tone?: Tone) => void>(() => {});

export function ToastProvider({ children }: { children: React.ReactNode }) {
  const [toasts, setToasts] = useState<Toast[]>([]);
  const nextId = useRef(1);

  const push = useCallback((message: string, tone: Tone = "ok") => {
    const id = nextId.current++;
    setToasts((current) => [...current, { id, message, tone }]);
    window.setTimeout(() => setToasts((current) => current.filter((t) => t.id !== id)), 4200);
  }, []);

  return (
    <ToastContext.Provider value={push}>
      {children}
      <div className="pointer-events-none fixed right-5 bottom-5 z-[70] flex flex-col gap-2">
        {toasts.map((toast) => (
          <div
            key={toast.id}
            role="status"
            className={cn(
              "animate-rise pointer-events-auto max-w-sm rounded-xl border px-4 py-3 text-sm shadow-2xl backdrop-blur",
              toast.tone === "ok" && "border-offer/30 bg-card text-ink",
              toast.tone === "err" && "border-reject/40 bg-card text-ink",
              toast.tone === "info" && "border-line bg-card text-ink",
            )}
          >
            <span
              className={cn(
                "mr-2 inline-block h-2 w-2 rounded-full align-middle",
                toast.tone === "ok" && "bg-offer",
                toast.tone === "err" && "bg-reject",
                toast.tone === "info" && "bg-applied",
              )}
            />
            {toast.message}
          </div>
        ))}
      </div>
    </ToastContext.Provider>
  );
}

export function useToast() {
  return useContext(ToastContext);
}
