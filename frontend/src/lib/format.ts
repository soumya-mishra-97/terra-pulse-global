// Display formatting only. Numbers are never computed here beyond scaling for display.

export function fmtPeople(v: number | null | undefined): string {
  if (v === null || v === undefined || !Number.isFinite(v)) return "Data unavailable";
  const a = Math.abs(v);
  const sign = v < 0 ? "-" : "";
  if (a >= 1e9) return `${sign}${(a / 1e9).toFixed(2)}B`;
  if (a >= 1e6) return `${sign}${(a / 1e6).toFixed(1)}M`;
  if (a >= 1e3) return `${sign}${(a / 1e3).toFixed(1)}K`;
  return `${sign}${a.toFixed(0)}`;
}

export function fmtExact(v: number | null | undefined): string {
  if (v === null || v === undefined || !Number.isFinite(v)) return "Data unavailable";
  return Math.round(v).toLocaleString("en-US");
}

export function fmtPct(v: number | null | undefined, digits = 2, signed = false): string {
  if (v === null || v === undefined || !Number.isFinite(v)) return "Data unavailable";
  const s = v.toFixed(digits);
  return `${signed && v > 0 ? "+" : ""}${s}%`;
}

export function fmtDate(iso: string | null | undefined): string {
  if (!iso) return "Data unavailable";
  const d = new Date(iso.length === 10 ? `${iso}T00:00:00Z` : iso);
  if (Number.isNaN(d.getTime())) return iso;
  return d.toLocaleDateString("en-GB", { day: "numeric", month: "short", year: "numeric", timeZone: "UTC" });
}

export function fmtDateTime(iso: string | null | undefined): string {
  if (!iso) return "-";
  const d = new Date(iso);
  return Number.isNaN(d.getTime()) ? iso : d.toLocaleString("en-GB", { dateStyle: "medium", timeStyle: "short" });
}

/** Illustrative exponential extrapolation used only for the labelled counter (mirrors domain/calculations.py). */
export function illustrativeValue(base: number, baseDateIso: string, ratePct: number, at: Date): number {
  const years = (at.getTime() - new Date(`${baseDateIso}T00:00:00Z`).getTime()) / (365.2425 * 86400000);
  return base * Math.exp((ratePct / 100) * years);
}

export function flagEmoji(iso2: string | null | undefined): string {
  if (!iso2 || !/^[A-Za-z]{2}$/.test(iso2)) return "";
  return String.fromCodePoint(...iso2.toUpperCase().split("").map((c) => 0x1f1e6 + c.charCodeAt(0) - 65));
}
