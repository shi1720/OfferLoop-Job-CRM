import { describe, expect, it } from "vitest";

import { cn, daysSince, initials, stalenessTone, timeAgo } from "./format";

const NOW = new Date("2026-09-02T12:00:00Z");

describe("daysSince", () => {
  it("counts whole days and never goes negative", () => {
    expect(daysSince("2026-08-27T12:00:00Z", NOW)).toBe(6);
    expect(daysSince("2026-09-03T12:00:00Z", NOW)).toBe(0);
  });
});

describe("timeAgo", () => {
  it("scales through units", () => {
    expect(timeAgo("2026-09-02T11:59:40Z", NOW)).toBe("just now");
    expect(timeAgo("2026-09-02T11:20:00Z", NOW)).toBe("40m ago");
    expect(timeAgo("2026-09-02T03:00:00Z", NOW)).toBe("9h ago");
    expect(timeAgo("2026-08-30T12:00:00Z", NOW)).toBe("3d ago");
    expect(timeAgo("2026-08-10T12:00:00Z", NOW)).toBe("3w ago");
  });
});

describe("stalenessTone", () => {
  it("matches the cadence thresholds", () => {
    expect(stalenessTone(0)).toBe("fresh");
    expect(stalenessTone(5)).toBe("warm");
    expect(stalenessTone(10)).toBe("hot");
  });
});

describe("initials", () => {
  it("takes the first two words", () => {
    expect(initials("Shivam Gupta")).toBe("SG");
    expect(initials("Finlo")).toBe("F");
    expect(initials("  ")).toBe("?");
  });
});

describe("cn", () => {
  it("drops falsy parts", () => {
    expect(cn("a", false, undefined, "b", null)).toBe("a b");
  });
});
