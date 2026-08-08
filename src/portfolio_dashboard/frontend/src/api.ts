import type {
  ArbitrumPayload,
  InvestmentPayload,
  OptionsPayload,
  RealEstatePayload,
  RefreshJob,
  RefreshKind
} from "./types";

const apiBaseUrl =
  (import.meta as ImportMeta & { env?: Record<string, string | undefined> }).env
    ?.VITE_DASHBOARD_API_URL ?? "";

async function getJson<T>(url: string): Promise<T> {
  const response = await fetch(`${apiBaseUrl}${url}`);
  if (!response.ok) {
    throw new Error(`Request failed: ${response.status}`);
  }
  return response.json() as Promise<T>;
}

export function fetchOptions(): Promise<OptionsPayload> {
  return getJson<OptionsPayload>("/api/options");
}

export function fetchStocks(params: URLSearchParams): Promise<InvestmentPayload> {
  return getJson<InvestmentPayload>(`/api/stocks?${params.toString()}`);
}

export function fetchNexo(params: URLSearchParams): Promise<InvestmentPayload> {
  return getJson<InvestmentPayload>(`/api/nexo?${params.toString()}`);
}

export function fetchArbitrum(params: URLSearchParams): Promise<ArbitrumPayload> {
  return getJson<ArbitrumPayload>(`/api/arbitrum?${params.toString()}`);
}

export function fetchRealEstate(params: URLSearchParams): Promise<RealEstatePayload> {
  return getJson<RealEstatePayload>(`/api/real-estate?${params.toString()}`);
}

export async function startRefresh(kind: RefreshKind): Promise<RefreshJob> {
  const response = await fetch(`${apiBaseUrl}/api/refresh/${kind}`, { method: "POST" });
  if (!response.ok) {
    const payload = (await response.json().catch(() => null)) as { detail?: string } | null;
    throw new Error(payload?.detail ?? `Request failed: ${response.status}`);
  }
  return response.json() as Promise<RefreshJob>;
}

export function fetchRefreshJob(jobId: string): Promise<RefreshJob> {
  return getJson<RefreshJob>(`/api/refresh/jobs/${jobId}`);
}

export async function stopServer(): Promise<void> {
  const response = await fetch(`${apiBaseUrl}/api/server/stop`, { method: "POST" });
  if (!response.ok) {
    throw new Error(`Request failed: ${response.status}`);
  }
}
