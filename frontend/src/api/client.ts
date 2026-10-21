// Thin fetch wrapper. The browser never holds LLM credentials: every AI call goes through /api.
import type {
  Architecture, ChatResponse, CityPage, CountryPage, Health, HistoryResponse, RegionsResponse, ReportCountry, ReportDetail,
  ReportOptions, ReportPage, ReportSummary, WorldSummary,
} from "./types";

export class ApiError extends Error {
  constructor(public status: number, message: string, public requestId?: string) {
    super(message);
  }
}

const USER_KEY = "terrapulse.user";
export function currentUser(): string {
  try {
    return localStorage.getItem(USER_KEY) || "demo-user";
  } catch {
    return "demo-user";
  }
}

function describe(detail: unknown): string {
  if (typeof detail === "string") return detail;
  if (Array.isArray(detail)) return detail.map((d) => (d && typeof d === "object" && "msg" in d ? String(d.msg) : String(d))).join("; ");
  return "Request failed";
}

async function request<T>(path: string, init: RequestInit = {}, timeoutMs = 30000): Promise<T> {
  const ctrl = new AbortController();
  const timer = setTimeout(() => ctrl.abort(), timeoutMs);
  try {
    const res = await fetch(path, {
      ...init,
      signal: init.signal ?? ctrl.signal,
      headers: { "Content-Type": "application/json", "X-User-Id": currentUser(), ...(init.headers ?? {}) },
    });
    if (!res.ok) {
      let message = `${res.status} ${res.statusText}`;
      try {
        const body = await res.json();
        message = describe(body?.error?.detail ?? body?.detail ?? message);
      } catch { /* non-JSON error body */ }
      if (res.status === 429) message = "You're sending requests too quickly. Please wait a moment.";
      throw new ApiError(res.status, message, res.headers.get("X-Request-ID") ?? undefined);
    }
    if (res.status === 204) return undefined as T;
    return (await res.json()) as T;
  } catch (e) {
    if (e instanceof DOMException && e.name === "AbortError") throw new ApiError(0, "The request timed out. Please try again.");
    if (e instanceof TypeError) throw new ApiError(0, "Cannot reach the TerraPulse API. Is the backend running?");
    throw e;
  } finally {
    clearTimeout(timer);
  }
}

export const api = {
  health: () => request<Health>("/api/v1/health"),
  summary: () => request<WorldSummary>("/api/v1/population/summary"),
  countries: (p: { q?: string; region?: string; sort?: string; order?: string; limit?: number; offset?: number } = {}) => {
    const qs = new URLSearchParams(Object.entries(p).filter(([, v]) => v !== undefined && v !== "").map(([k, v]) => [k, String(v)]));
    return request<CountryPage>(`/api/v1/population/countries?${qs}`);
  },
  history: (iso3: string, metric = "population_total", start?: number) =>
    request<HistoryResponse>(`/api/v1/population/countries/${encodeURIComponent(iso3)}/history?metric=${metric}${start ? `&start=${start}` : ""}`),
  regions: () => request<RegionsResponse>("/api/v1/population/regions"),
  cities: (q: string) => request<CityPage>(`/api/v1/population/cities?q=${encodeURIComponent(q)}`),
  chat: (question: string, signal?: AbortSignal) =>
    request<ChatResponse>("/api/v1/copilot/chat", { method: "POST", body: JSON.stringify({ question }), signal }, 120000),
  architecture: () => request<Architecture>("/api/v1/copilot/architecture"),
  doc: (slug: string) => request<{ slug: string; title: string; markdown: string }>(`/api/v1/docs/${slug}`),
  reportCountries: () => request<ReportCountry[]>("/api/v1/reports/countries"),
  reportOptions: () => request<ReportOptions>("/api/v1/reports/options"),
  generateReport: (body: { country_code: string; period: string; sections: string[] }, idempotencyKey: string) =>
    request<ReportSummary>("/api/v1/reports/generate", { method: "POST", body: JSON.stringify(body), headers: { "Idempotency-Key": idempotencyKey } }),
  regenerateReport: (id: string) => request<ReportSummary>(`/api/v1/reports/${id}/regenerate`, { method: "POST" }),
  report: (id: string) => request<ReportDetail>(`/api/v1/reports/${id}`),
  reports: (limit = 20, offset = 0) => request<ReportPage>(`/api/v1/reports?limit=${limit}&offset=${offset}`),
  deleteReport: (id: string) => request<void>(`/api/v1/reports/${id}`, { method: "DELETE" }),
};

/** Download through fetch so the X-User-Id header is sent; then hand the blob to the browser. */
export async function downloadReport(id: string, format: "pdf" | "md"): Promise<void> {
  const res = await fetch(`/api/v1/reports/${id}/download?format=${format}`, { headers: { "X-User-Id": currentUser() } });
  if (!res.ok) throw new ApiError(res.status, res.status === 409 ? "The report is not ready yet." : "Download failed.");
  const blob = await res.blob();
  const cd = res.headers.get("Content-Disposition") ?? "";
  const name = /filename="([^"]+)"/.exec(cd)?.[1] ?? `terrapulse-report.${format}`;
  const url = URL.createObjectURL(blob);
  const a = document.createElement("a");
  a.href = url;
  a.download = name;
  document.body.appendChild(a);
  a.click();
  a.remove();
  setTimeout(() => URL.revokeObjectURL(url), 1000);
}
