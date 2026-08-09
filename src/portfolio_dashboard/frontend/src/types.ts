export type Option = {
  label: string;
  value: string;
  group?: string;
  region?: string;
  provider?: string;
  currency?: string;
};

export type Metric = {
  label: string;
  value: number;
  display: string;
};

export type TablePayload = {
  columns: string[];
  rows: Record<string, string | number | null>[];
};

export type BreakdownItem = {
  label: string;
  value: number;
};

export type CompositionPayload =
  | { kind: "breakdown"; items: { label: string; value: number }[] }
  | { kind: "metadata"; items: { label: string; value: string }[] }
  | { kind: "empty"; items: [] };

export type InvestmentPayload = {
  title: string;
  startDate: string;
  metrics: Metric[];
  composition: CompositionPayload;
  history: Record<string, string | number | null>[];
  transactions: TablePayload;
};

export type RealEstatePayload = {
  startDate: string;
  metrics: Metric[];
  valueEquity: Record<string, string | number | null>[];
  cashflow: Record<string, string | number | null>[];
  profitLoss: Record<string, string | number | null>[];
  mortgageBalances: Record<string, string | number | null>[];
  outflows: BreakdownItem[];
  inflows: BreakdownItem[];
  mortgages: TablePayload;
  recentOutflows: TablePayload;
  recentInflows: TablePayload;
};

export type ArbitrumPayload = {
  title: string;
  startDate: string;
  metrics: Metric[];
  transactionHistory: Record<string, string | number | null>[];
  history: Record<string, string | number | null>[];
  composition: CompositionPayload;
  sources: TablePayload;
  transactions: TablePayload;
  warnings: string[];
};

export type OptionsPayload = {
  stocks: Option[];
  nexo: Option[];
  arbitrum: Option[];
};

export type RefreshKind = "prices" | "transactions" | "crypto" | "all";

export type RefreshJob = {
  id: string;
  kind: RefreshKind;
  status: "queued" | "running" | "succeeded" | "failed";
  createdAt: string;
  startedAt: string | null;
  finishedAt: string | null;
  currentStep: string | null;
  error: string | null;
  logs: string[];
};
