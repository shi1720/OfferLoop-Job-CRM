/** Small formatting helpers shared across the UI. */

export function cn(...parts: Array<string | false | null | undefined>): string {
  return parts.filter(Boolean).join(" ");
}

export function daysSince(iso: string, now: Date = new Date()): number {
  const then = new Date(iso).getTime();
  return Math.max(0, Math.floor((now.getTime() - then) / 86_400_000));
}

export function timeAgo(iso: string, now: Date = new Date()): string {
  const seconds = Math.floor((now.getTime() - new Date(iso).getTime()) / 1000);
  if (seconds < 60) return "just now";
  const minutes = Math.floor(seconds / 60);
  if (minutes < 60) return `${minutes}m ago`;
  const hours = Math.floor(minutes / 60);
  if (hours < 24) return `${hours}h ago`;
  const days = Math.floor(hours / 24);
  if (days < 7) return `${days}d ago`;
  const weeks = Math.floor(days / 7);
  if (weeks < 5) return `${weeks}w ago`;
  const months = Math.floor(days / 30);
  return `${months}mo ago`;
}

export function shortDate(iso: string): string {
  return new Date(iso).toLocaleDateString("en-IN", { day: "numeric", month: "short" });
}

export function longDate(iso: string): string {
  return new Date(iso).toLocaleDateString("en-IN", { day: "numeric", month: "short", year: "numeric" });
}

/** Staleness tone for the "ghost meter": fresh → warm → burning. */
export function stalenessTone(quietDays: number): "fresh" | "warm" | "hot" {
  if (quietDays >= 10) return "hot";
  if (quietDays >= 5) return "warm";
  return "fresh";
}

export function initials(name: string): string {
  const words = name.trim().split(/\s+/).filter(Boolean);
  if (words.length === 0) return "?";
  return words
    .slice(0, 2)
    .map((w) => w[0]!.toUpperCase())
    .join("");
}
