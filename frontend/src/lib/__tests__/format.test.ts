import { describe, expect, it } from "vitest";
import { flagEmoji, fmtPct, fmtPeople, illustrativeValue } from "../format";

describe("format", () => {
  it("formats people with explicit missing-data text", () => {
    expect(fmtPeople(8_215_424_893)).toBe("8.22B");
    expect(fmtPeople(237_500_000)).toBe("237.5M");
    expect(fmtPeople(null)).toBe("Data unavailable");
  });
  it("formats signed percentages", () => {
    expect(fmtPct(0.9113, 2, true)).toBe("+0.91%");
    expect(fmtPct(-0.17, 2, true)).toBe("-0.17%");
  });
  it("mirrors the backend illustrative exponential projection", () => {
    const base = 8e9;
    const oneYear = new Date(Date.parse("2025-07-01T00:00:00Z") + 365.2425 * 86400000);
    expect(illustrativeValue(base, "2025-07-01", 1, oneYear)).toBeCloseTo(base * Math.exp(0.01), -1);
  });
  it("builds flag emoji only for valid ISO2 codes", () => {
    expect(flagEmoji("IN")).toBe("🇮🇳");
    expect(flagEmoji("1W")).toBe("");
  });
});
