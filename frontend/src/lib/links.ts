/** Zero-OAuth integrations: Gmail compose and Google Calendar template
 * links. Pure functions — unit-tested, no network, work on any device. */

function encode(value: string): string {
  return encodeURIComponent(value);
}

/** Gmail's compose deep link. Falls back gracefully: if the user isn't in
 * Gmail the page shows Google's account chooser, and `mailto:` remains the
 * escape hatch for native-mail people. */
export function gmailComposeUrl(opts: { to?: string; subject?: string; body?: string }): string {
  const params = [
    "view=cm",
    "fs=1",
    opts.to ? `to=${encode(opts.to)}` : "",
    opts.subject ? `su=${encode(opts.subject)}` : "",
    opts.body ? `body=${encode(opts.body)}` : "",
  ]
    .filter(Boolean)
    .join("&");
  return `https://mail.google.com/mail/?${params}`;
}

export function mailtoUrl(opts: { to?: string; subject?: string; body?: string }): string {
  const params = [
    opts.subject ? `subject=${encode(opts.subject)}` : "",
    opts.body ? `body=${encode(opts.body)}` : "",
  ]
    .filter(Boolean)
    .join("&");
  return `mailto:${opts.to ?? ""}${params ? `?${params}` : ""}`;
}

/** Format a Date as Google Calendar's UTC stamp: YYYYMMDDTHHMMSSZ. */
export function calendarStamp(date: Date): string {
  return date.toISOString().replace(/[-:]/g, "").replace(/\.\d{3}/, "");
}

/** "Add to Google Calendar" template link — no OAuth, opens prefilled. */
export function calendarEventUrl(opts: {
  title: string;
  start: Date;
  durationMinutes?: number;
  details?: string;
  location?: string;
}): string {
  const end = new Date(opts.start.getTime() + (opts.durationMinutes ?? 60) * 60_000);
  const params = [
    "action=TEMPLATE",
    `text=${encode(opts.title)}`,
    `dates=${calendarStamp(opts.start)}/${calendarStamp(end)}`,
    opts.details ? `details=${encode(opts.details)}` : "",
    opts.location ? `location=${encode(opts.location)}` : "",
  ]
    .filter(Boolean)
    .join("&");
  return `https://calendar.google.com/calendar/render?${params}`;
}
