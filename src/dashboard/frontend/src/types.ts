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
  status?: "OK" | "WARN" | "CRIT" | string;
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
  asOfDate: string;
  fromDate: string;
  startDate: string;
  summary: {
    title: string;
    empty?: boolean;
    currentValue?: number;
    profitLoss?: number;
    metrics: Metric[];
  };
  composition: CompositionPayload;
  history: Record<string, string | number | null>[];
  transactions: TablePayload;
};

export type RealEstatePayload = {
  title: string;
  asOfDate: string;
  fromDate: string;
  startDate: string;
  summary: {
    title: string;
    metrics: Metric[];
  };
  valueEquity: Record<string, string | number | null>[];
  cashflow: Record<string, string | number | null>[];
  plBreakdown: Record<string, string | number | null>[];
  mortgageBalance: Record<string, string | number | null>[];
  outflowBreakdown: BreakdownItem[];
  inflowBreakdown: BreakdownItem[];
  mortgageSummary: TablePayload;
  recentOutflows: TablePayload;
  recentInflows: TablePayload;
  warnings: string[];
};

export type ArbitrumPayload = {
  title: string;
  fromDate: string;
  startDate: string;
  currency: "EUR" | "USD" | string;
  mode: "full" | "name" | string;
  selection: string;
  summary: {
    title: string;
    empty?: boolean;
    currentValue?: number;
    profitLoss?: number;
    metrics: Metric[];
  };
  transactionsDaily: Record<string, string | number | null>[];
  valueHistory: Record<string, string | number | null>[];
  composition: CompositionPayload;
  sourceBreakdown: TablePayload;
  transactions: TablePayload;
  warnings: string[];
};

export type OptionsPayload = {
  stocks: {
    analysisModes: Option[];
    compositionModes: Option[];
    assets: Option[];
  };
  nexo: {
    analysisModes: Option[];
    compositionModes: Option[];
    assets: Option[];
  };
  arbitrum: {
    analysisModes: Option[];
    compositionModes: Option[];
    assets: Option[];
    currencies: Option[];
  };
  realEstate: {
    assets: Option[];
  };
};
