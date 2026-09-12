import { describe, expect, it } from "vitest";

import { calendarEventUrl, calendarStamp, gmailComposeUrl, mailtoUrl } from "./links";

describe("gmailComposeUrl", () => {
  it("prefills to, subject and body", () => {
    const url = gmailComposeUrl({ to: "priya@finlo.dev", subject: "Following up: SDE II", body: "Hi Priya,\n\nJust checking in." });
    expect(url).toContain("https://mail.google.com/mail/?view=cm&fs=1");
    expect(url).toContain("to=priya%40finlo.dev");
    expect(url).toContain("su=Following%20up%3A%20SDE%20II");
    expect(url).toContain("body=Hi%20Priya%2C%0A%0AJust%20checking%20in.");
  });

  it("omits empty fields", () => {
    expect(gmailComposeUrl({ body: "hello" })).not.toContain("to=");
  });
});

describe("mailtoUrl", () => {
  it("builds a valid mailto with query", () => {
    expect(mailtoUrl({ to: "a@b.c", subject: "Hi" })).toBe("mailto:a@b.c?subject=Hi");
  });
});

describe("calendar links", () => {
  it("formats the UTC stamp Google expects", () => {
    expect(calendarStamp(new Date("2026-10-01T09:30:00Z"))).toBe("20261001T093000Z");
  });

  it("builds a one-hour event by default", () => {
    const url = calendarEventUrl({
      title: "Interview: SDE II at Finlo",
      start: new Date("2026-10-01T09:30:00Z"),
      location: "Bengaluru",
    });
    expect(url).toContain("calendar.google.com/calendar/render?action=TEMPLATE");
    expect(url).toContain("dates=20261001T093000Z/20261001T103000Z");
    expect(url).toContain("location=Bengaluru");
  });
});
