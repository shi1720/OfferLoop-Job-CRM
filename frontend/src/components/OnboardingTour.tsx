/** First-run guided tour: a moving spotlight cutout + an arrowed step card.
 *
 * Auto-starts once for any profile with `onboarded: false`, then records
 * completion server-side so it never nags again. Replayable any time via
 * the "?" button in the sidebar (a `offerloop:tour` window event). */

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { BellRing, FileUp, Kanban, KeyRound, Link2, Radar, Sunrise } from "lucide-react";
import { useCallback, useEffect, useRef, useState } from "react";
import { useLocation, useNavigate } from "react-router-dom";

import { api } from "../api";
import { cn } from "../lib/format";
import { Button } from "./ui";

export const TOUR_EVENT = "offerloop:tour";

export function replayTour() {
  window.dispatchEvent(new CustomEvent(TOUR_EVENT));
}

interface TourStep {
  target: string; // matches a [data-tour="…"] attribute
  route?: string; // navigate here before spotlighting
  icon: React.ReactNode;
  title: string;
  body: string;
}

const STEPS: TourStep[] = [
  {
    target: "nav-today",
    route: "/",
    icon: <Sunrise size={15} />,
    title: "Start every day here",
    body: "Today shows exactly what moves your search forward right now: follow-ups due with drafts attached, interviews coming up, and your weekly goal.",
  },
  {
    target: "nav-pipeline",
    route: "/pipeline",
    icon: <Kanban size={15} />,
    title: "Your pipeline, on one board",
    body: "Every application is a card. Drag it from Applied to Interview to Offer — the full journey is recorded for you, like deals in a sales CRM.",
  },
  {
    target: "quick-add",
    route: "/pipeline",
    icon: <Link2 size={15} />,
    title: "Add a job in seconds",
    body: "Paste any posting link — or the whole job description — and Gemini fills in the card for you. Every application you log earns +10 momentum.",
  },
  {
    target: "scan",
    route: "/pipeline",
    icon: <Radar size={15} />,
    title: "The nudge engine",
    body: "OfferLoop scans your pipeline every hour and works out exactly who to follow up with today. This button runs a scan on demand.",
  },
  {
    target: "nav-nudges",
    icon: <BellRing size={15} />,
    title: "Nudges arrive pre-written",
    body: "Every follow-up nudge comes with a draft written in your voice, grounded on your profile and your own past drafts. Review, personalize, send — +15 momentum.",
  },
  {
    target: "nav-import",
    icon: <FileUp size={15} />,
    title: "Bring your whole search",
    body: "Import the CSVs you already have — spreadsheets, or exports from Teal and Huntr — and postings, drafts and stages link up automatically. +25 momentum.",
  },
  {
    target: "nav-profile",
    icon: <KeyRound size={15} />,
    title: "Make it sound like you",
    body: "Under Profile & voice, add your skills, proof points and writing rules so every draft is grounded in facts — and when you want unlimited AI drafts, your free Gemini key lives there too.",
  },
];

interface Rect {
  top: number;
  left: number;
  width: number;
  height: number;
}

const CARD_WIDTH = 336;
const MARGIN = 14;

function clamp(value: number, min: number, max: number) {
  return Math.min(Math.max(value, min), max);
}

export function OnboardingTour() {
  const queryClient = useQueryClient();
  const navigate = useNavigate();
  const location = useLocation();
  const { data: profile } = useQuery({ queryKey: ["profile"], queryFn: api.profile.get });

  const [active, setActive] = useState(false);
  const [index, setIndex] = useState(0);
  const [rect, setRect] = useState<Rect | null>(null);
  const autoStarted = useRef(false);

  const finish = useMutation({
    mutationFn: () => api.profile.update({ onboarded: true }),
    onSuccess: () => void queryClient.invalidateQueries({ queryKey: ["profile"] }),
  });

  const start = useCallback(() => {
    setIndex(0);
    setRect(null);
    setActive(true);
    if (location.pathname !== "/") navigate("/");
  }, [location.pathname, navigate]);

  const close = useCallback(() => {
    setActive(false);
    if (profile && !profile.onboarded) finish.mutate();
  }, [profile, finish]);

  // Auto-start exactly once for fresh accounts, after the page has painted.
  // Desktop only: the sidebar targets live behind a menu on small screens,
  // where the activation checklist carries the introduction instead.
  useEffect(() => {
    if (profile && !profile.onboarded && !autoStarted.current && window.innerWidth >= 768) {
      autoStarted.current = true;
      const timer = window.setTimeout(start, 700);
      return () => window.clearTimeout(timer);
    }
  }, [profile, start]);

  // Steps can live on different routes — follow them.
  useEffect(() => {
    if (!active) return;
    const route = STEPS[index].route;
    if (route && location.pathname !== route) navigate(route);
  }, [active, index, location.pathname, navigate]);

  // Replay from anywhere in the app — desktop only, same as auto-start:
  // on a phone the targets live inside a closed slide-over menu.
  useEffect(() => {
    const handler = () => {
      if (window.innerWidth >= 768) start();
    };
    window.addEventListener(TOUR_EVENT, handler);
    return () => window.removeEventListener(TOUR_EVENT, handler);
  }, [start]);

  useEffect(() => {
    if (!active) return;
    const onKey = (event: KeyboardEvent) => event.key === "Escape" && close();
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [active, close]);

  // Measure the current step's target; retry while the route settles.
  useEffect(() => {
    if (!active) return;
    let raf = 0;
    let tries = 0;
    const measure = () => {
      const el = document.querySelector(`[data-tour="${STEPS[index].target}"]`);
      const r = el?.getBoundingClientRect();
      if (!r || r.width === 0) {
        if (tries++ < 60) raf = requestAnimationFrame(measure);
        return;
      }
      setRect({ top: r.top, left: r.left, width: r.width, height: r.height });
    };
    measure();
    window.addEventListener("resize", measure);
    return () => {
      cancelAnimationFrame(raf);
      window.removeEventListener("resize", measure);
    };
  }, [active, index, location.pathname]);

  if (!active || !rect) return null;

  const step = STEPS[index];
  const last = index === STEPS.length - 1;

  // Card placement: right of the target when there's room, else below/above.
  const pad = 6;
  const spot = { top: rect.top - pad, left: rect.left - pad, width: rect.width + pad * 2, height: rect.height + pad * 2 };
  let side: "right" | "bottom" | "top" = "right";
  if (spot.left + spot.width + CARD_WIDTH + MARGIN * 2 > window.innerWidth) {
    side = spot.top + spot.height + 240 < window.innerHeight ? "bottom" : "top";
  }
  const card =
    side === "right"
      ? {
          left: spot.left + spot.width + MARGIN,
          top: clamp(spot.top + spot.height / 2 - 90, MARGIN, window.innerHeight - 260),
        }
      : {
          left: clamp(spot.left + spot.width / 2 - CARD_WIDTH / 2, MARGIN, window.innerWidth - CARD_WIDTH - MARGIN),
          top: side === "bottom" ? spot.top + spot.height + MARGIN : Math.max(MARGIN, spot.top - 240),
        };
  const arrow =
    side === "right"
      ? { left: -5, top: clamp(spot.top + spot.height / 2 - card.top - 5, 14, 200) }
      : side === "bottom"
        ? { top: -5, left: clamp(spot.left + spot.width / 2 - card.left - 5, 14, CARD_WIDTH - 24) }
        : { bottom: -5, left: clamp(spot.left + spot.width / 2 - card.left - 5, 14, CARD_WIDTH - 24) };

  return (
    <div className="fixed inset-0 z-[80]" role="dialog" aria-modal="true" aria-label="OfferLoop tour">
      {/* Spotlight: everything but the target dims; the cutout glides between steps. */}
      <div
        className="absolute rounded-xl ring-2 ring-accent/80 transition-all duration-300 ease-out"
        style={{ ...spot, boxShadow: "0 0 0 9999px rgba(5, 8, 14, 0.78)" }}
      />

      <div
        className="ring-card absolute rounded-2xl bg-card p-4 shadow-2xl transition-all duration-300 ease-out"
        style={{ width: CARD_WIDTH, ...card }}
      >
        <span className="absolute h-2.5 w-2.5 rotate-45 bg-card" style={arrow} aria-hidden />

        <div className="flex items-center justify-between">
          <span className="flex h-7 w-7 items-center justify-center rounded-lg bg-accent/10 text-accent">
            {step.icon}
          </span>
          <span className="flex items-center gap-1.5" aria-label={`Step ${index + 1} of ${STEPS.length}`}>
            {STEPS.map((_, i) => (
              <span
                key={i}
                className={cn(
                  "h-1.5 rounded-full transition-all",
                  i === index ? "w-4 bg-accent" : "w-1.5 bg-raised",
                  i < index && "bg-accent/40",
                )}
              />
            ))}
          </span>
        </div>

        <h3 className="font-display mt-3 text-[15px] font-bold tracking-tight">{step.title}</h3>
        <p className="mt-1 text-[13px] leading-relaxed text-ink-2">{step.body}</p>

        <div className="mt-4 flex items-center justify-between">
          <button onClick={close} className="cursor-pointer text-xs text-ink-3 transition-colors hover:text-ink-2">
            Skip tour
          </button>
          <div className="flex items-center gap-2">
            {index > 0 && (
              <Button className="!px-3 !py-1.5" onClick={() => setIndex((i) => i - 1)}>
                Back
              </Button>
            )}
            <Button
              variant="primary"
              className="!px-3 !py-1.5"
              onClick={() => (last ? close() : setIndex((i) => i + 1))}
            >
              {last ? "Start building momentum" : "Next"}
            </Button>
          </div>
        </div>
      </div>
    </div>
  );
}
