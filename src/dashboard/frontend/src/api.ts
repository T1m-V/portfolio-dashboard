import type { InvestmentPayload, OptionsPayload, RealEstatePayload } from "./types";

async function getJson<T>(url: string): Promise<T> {
  const response = await fetch(url);
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

export function fetchRealEstate(params: URLSearchParams): Promise<RealEstatePayload> {
  return getJson<RealEstatePayload>(`/api/real-estate?${params.toString()}`);
}
