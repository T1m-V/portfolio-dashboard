import {
  Area,
  Bar,
  CartesianGrid,
  Cell,
  ComposedChart,
  Legend,
  Line,
  Pie,
  PieChart,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis
} from "recharts";
import {
  Activity,
  Building2,
  ChevronDown,
  Coins,
  Database,
  Eye,
  EyeOff,
  Gauge,
  LayoutDashboard,
  Layers3,
  Menu,
  Power,
  RefreshCcw,
  ShieldCheck,
  WalletCards,
  X
} from "lucide-react";
import { useCallback, useEffect, useMemo, useState } from "react";
import type React from "react";
import {
  fetchArbitrum,
  fetchNexo,
  fetchOptions,
  fetchRealEstate,
  fetchRefreshJob,
  fetchStocks,
  startRefresh,
  stopServer
} from "./api";
import type {
  ArbitrumPayload,
  CompositionPayload,
  BreakdownItem,
  InvestmentPayload,
  Metric,
  Option,
  OptionsPayload,
  RealEstatePayload,
  RefreshJob,
  RefreshKind,
  TablePayload
} from "./types";

type TabKey = "overview" | "stocks" | "nexo" | "arbitrum" | "realEstate";
type PeriodKey = "mtd" | "ytd" | "1y" | "3y" | "5y" | "sinceStart" | "custom";

const tabs: { key: TabKey; label: string; icon: typeof WalletCards }[] = [
  { key: "overview", label: "Overview", icon: LayoutDashboard },
  { key: "stocks", label: "Stocks", icon: WalletCards },
  { key: "nexo", label: "NEXO", icon: Coins },
  { key: "arbitrum", label: "Arbitrum", icon: ShieldCheck },
  { key: "realEstate", label: "Real Estate", icon: Building2 }
];

const ALL = "ALL";
const allOption: Option = { label: "All", value: ALL };
const stockDimensions: Option[] = [
  { label: "Asset Group", value: "group" },
  { label: "Region", value: "region" },
  { label: "Provider", value: "provider" },
  { label: "Asset", value: "name" }
];
const stockCompositions: Option[] = [
  { label: "Asset Name", value: "name" },
  { label: "Asset Group", value: "group" },
  { label: "Region", value: "region" },
  { label: "Provider", value: "provider" }
];
const currencies: Option[] = [
  { label: "EUR", value: "EUR" },
  { label: "USD", value: "USD" }
];
const accentColors = ["#2df2c9", "#b7ff5a", "#7aa7ff", "#ff63a5", "#f6d45d", "#9c7bff"];
const valueColumnTokens = [
  "amount",
  "capital",
  "cash",
  "cost",
  "dividend",
  "equity",
  "fee",
  "interest",
  "market value",
  "mortgage",
  "outstanding",
  "p/l",
  "price",
  "principal",
  "profit",
  "tax",
  "usd equivalent",
  "value"
];
const periodOptions: { key: Exclude<PeriodKey, "custom">; label: string }[] = [
  { key: "mtd", label: "MTD" },
  { key: "ytd", label: "YTD" },
  { key: "1y", label: "1y" },
  { key: "3y", label: "3y" },
  { key: "5y", label: "5y" },
  { key: "sinceStart", label: "Since start" }
];

const friendlyLabels: Record<string, string> = {
  ALL_WORLD: "Global",
  DEVELOPED: "Developed markets",
  EMERGING: "Emerging markets",
  EUROPE: "Europe",
  US: "United States",
  AVOIDED_RENT: "Avoided rent",
  HYPOTHEEKRENTE_AFTREK: "Mortgage interest tax relief",
  DIRECT: "Direct",
  "Cost: OZB": "Property tax (OZB)"
};

const metricDescriptions: Record<string, string> = {
  "Net worth": "Investable assets plus property equity, after mortgage liabilities.",
  "Investable assets": "Stocks, NEXO, and Arbitrum positions at the selected end date.",
  "Property equity": "Property value less outstanding mortgage principal.",
  Liabilities: "Outstanding mortgage principal at the selected end date.",
  "Current Value": "Market value at the selected end date.",
  "Net P/L": "Profit or loss generated within the selected period.",
  "Period P/L": "Combined profit or loss generated within the selected period.",
  "Opening Value": "Market value at the beginning of the selected period.",
  "Opening net worth": "Combined net worth at the beginning of the selected period.",
  "Net Invested": "Net deposits, purchases, sales, and withdrawals within the selected period.",
  "Interest earned": "Interest credited within the selected period.",
  Dividends: "Dividend income received within the selected period.",
  "Property Value": "Latest property valuation available at the selected end date.",
  "Gross mortgage debt": "Mortgage principal owed at the selected end date, before offsetting receivables.",
  "Loan receivable": "Principal still owed back to the portfolio at the selected end date.",
  "Estimated Equity": "Property value less outstanding mortgage principal.",
  "Period net cash flow": "Inflows minus property and financing outflows within the selected period.",
  LTV: "Gross mortgage debt divided by property value."
};

function todayIso(): string {
  return new Date().toISOString().slice(0, 10);
}

function parseIsoDate(value: string): { year: number; month: number; day: number } {
  const [year, month, day] = value.split("-").map(Number);
  return { year, month, day };
}

function isoDate(year: number, month: number, day: number): string {
  return `${year.toString().padStart(4, "0")}-${month.toString().padStart(2, "0")}-${day
    .toString()
    .padStart(2, "0")}`;
}

function daysInMonth(year: number, month: number): number {
  return new Date(Date.UTC(year, month, 0)).getUTCDate();
}

function shiftYears(value: string, years: number): string {
  const date = parseIsoDate(value);
  const targetYear = date.year - years;
  const targetDay = Math.min(date.day, daysInMonth(targetYear, date.month));
  return isoDate(targetYear, date.month, targetDay);
}

function maxIso(left: string, right: string): string {
  return left > right ? left : right;
}

function minIso(left: string, right: string): string {
  return left < right ? left : right;
}

function clampFromDate(value: string, asOfDate: string, startDate?: string | null): string {
  const boundedToAsOf = minIso(value, asOfDate);
  return startDate ? maxIso(boundedToAsOf, startDate) : boundedToAsOf;
}

function periodStartDate(period: PeriodKey, asOfDate: string, startDate?: string | null): string | null {
  if (period === "custom") {
    return null;
  }
  const asOf = parseIsoDate(asOfDate);
  const calculated = {
    mtd: isoDate(asOf.year, asOf.month, 1),
    ytd: isoDate(asOf.year, 1, 1),
    "1y": shiftYears(asOfDate, 1),
    "3y": shiftYears(asOfDate, 3),
    "5y": shiftYears(asOfDate, 5),
    sinceStart: startDate ?? null
  }[period];
  return calculated ? clampFromDate(calculated, asOfDate, startDate) : null;
}

function shouldRoundToWhole(value: number): boolean {
  return Math.abs(value) > 100;
}

function formatNumber(value: unknown): string {
  if (typeof value !== "number") {
    return String(value ?? "");
  }
  return value.toLocaleString(undefined, { maximumFractionDigits: shouldRoundToWhole(value) ? 0 : 2 });
}

function formatValue(value: unknown): string {
  if (typeof value !== "number") {
    return String(value ?? "");
  }
  if (shouldRoundToWhole(value)) {
    return value.toLocaleString(undefined, { maximumFractionDigits: 0 });
  }
  return value.toLocaleString(undefined, {
    minimumFractionDigits: 2,
    maximumFractionDigits: 2
  });
}

function formatMetric(metric: Metric): string {
  if (metric.label === "Transactions") {
    return Math.round(metric.value).toLocaleString();
  }
  if (metric.display.includes("%")) {
    return `${metric.value.toLocaleString(undefined, { maximumFractionDigits: 1 })}%`;
  }
  const currencyPrefix = metric.display.match(/^[A-Z]{3}\s/)?.[0] ?? "";
  return `${currencyPrefix}${formatValue(metric.value)}`;
}

function friendlyLabel(value: unknown): string {
  const text = String(value ?? "");
  return friendlyLabels[text] ?? text;
}

function formatTableValue(value: unknown, column: string): string {
  if (typeof value !== "number") {
    if (typeof value === "string" && /^[+-]?\d+(?:\.\d+)?e[+-]?\d+$/i.test(value)) {
      return Number(value).toLocaleString(undefined, { maximumFractionDigits: 12 });
    }
    return friendlyLabel(value);
  }
  const normalized = column.toLowerCase();
  if (normalized === "quantity") {
    return value.toLocaleString(undefined, { maximumFractionDigits: shouldRoundToWhole(value) ? 0 : 6 });
  }
  if (valueColumnTokens.some((token) => normalized.includes(token))) {
    return formatValue(value);
  }
  return formatNumber(value);
}

function optionValue(options: Option[], current: string): string {
  if (current && options.some((option) => option.value === current)) {
    return current;
  }
  return options[0]?.value ?? "";
}

function withAll(options: Option[]): Option[] {
  return [allOption, ...options.filter((option) => option.value !== allOption.value)];
}

function groupsForMode(options: Option[], mode: string): Option[] {
  if (mode === "name") {
    const counts = options.reduce<Map<string, number>>((result, option) => {
      result.set(option.label, (result.get(option.label) ?? 0) + 1);
      return result;
    }, new Map());
    return [...options]
      .map((option) => counts.get(option.label) === 1 ? option : { ...option, label: `${option.label} · ${option.value}` })
      .sort((left, right) => left.label.localeCompare(right.label));
  }
  const values = new Set<string>();
  for (const option of options) {
    const value = option[mode as keyof Option];
    if (typeof value === "string" && value) {
      values.add(value);
    }
  }
  return [...values].sort().map((value) => ({ label: friendlyLabel(value), value }));
}

function metricValue(metrics: Metric[], label: string): number {
  return metrics.find((metric) => metric.label === label)?.value ?? 0;
}

function latestDate(rows: Record<string, string | number | null>[]): string | null {
  return rows.reduce<string | null>((latest, row) => {
    const value = typeof row.Date === "string" ? row.Date.slice(0, 10) : "";
    return value && (!latest || value > latest) ? value : latest;
  }, null);
}

function displayDate(value: string | null): string {
  if (!value) {
    return "No dated data";
  }
  return new Intl.DateTimeFormat(undefined, { day: "numeric", month: "short", year: "numeric" })
    .format(new Date(`${value}T12:00:00`));
}

function investmentMetrics(
  metrics: Metric[],
  kind: "stocks" | "nexo",
  history: Record<string, string | number | null>[]
): Metric[] {
  const normalized = metrics.filter((metric) =>
    kind !== "nexo" || (!["Dividends"].includes(metric.label) && (!["Fees", "Taxes"].includes(metric.label) || metric.value !== 0))
  );
  const openingValue = history.find((row) => typeof row["Market Value"] === "number")?.["Market Value"];
  if (typeof openingValue !== "number") {
    return normalized;
  }
  const openingMetric: Metric = { label: "Opening Value", value: openingValue, display: "EUR " };
  return [normalized[0], openingMetric, ...normalized.slice(1)];
}

function flowTable(table: TablePayload): TablePayload {
  return {
    ...table,
    rows: table.rows.map((row) => ({
      ...row,
      Amount: typeof row.Amount === "number" ? Math.abs(row.Amount) : row.Amount
    }))
  };
}

function SelectField({
  label,
  value,
  options,
  disabled,
  onChange
}: {
  label: string;
  value: string;
  options: Option[];
  disabled?: boolean;
  onChange: (value: string) => void;
}) {
  return (
    <label className="field">
      <span>{label}</span>
      <div className="selectWrap">
        <select value={value} disabled={disabled} onChange={(event) => onChange(event.target.value)}>
          {options.map((option) => (
            <option key={option.value} value={option.value}>
              {option.label}
            </option>
          ))}
        </select>
        <ChevronDown size={16} />
      </div>
    </label>
  );
}

function DateField({
  label,
  value,
  max,
  onChange
}: {
  label: string;
  value: string;
  max?: string;
  onChange: (value: string) => void;
}) {
  return (
    <label className="field">
      <span>{label}</span>
      <input type="date" value={value} max={max} onChange={(event) => onChange(event.target.value)} />
    </label>
  );
}

function PeriodSelector({
  value,
  onChange
}: {
  value: PeriodKey;
  onChange: (value: Exclude<PeriodKey, "custom">) => void;
}) {
  return (
    <div className="field periodField">
      <span>Period</span>
      <div className="periodButtons">
        {periodOptions.map((option) => (
          <button
            className={value === option.key ? "active" : ""}
            key={option.key}
            type="button"
            onClick={() => onChange(option.key)}
          >
            {option.label}
          </button>
        ))}
      </div>
    </div>
  );
}

function SegmentedControl({
  label,
  value,
  options,
  onChange
}: {
  label: string;
  value: string;
  options: Option[];
  onChange: (value: string) => void;
}) {
  return (
    <div className="segmentedControl">
      <span>{label}</span>
      <div className="segmentButtons">
        {options.map((option) => (
          <button
            className={value === option.value ? "active" : ""}
            key={option.value}
            type="button"
            onClick={() => onChange(option.value)}
          >
            {option.label}
          </button>
        ))}
      </div>
    </div>
  );
}

function MetricStrip({ metrics }: { metrics: Metric[] }) {
  if (!metrics.length) {
    return <div className="emptyState">No metrics for this selection.</div>;
  }
  return (
    <section className="metricStrip">
      {metrics.map((metric) => {
        const directional = /p\/l|return|equity|value|worth|income|dividend|interest/i.test(metric.label);
        const tone = directional ? (metric.value < 0 ? "negative" : "positive") : "neutral";
        return (
          <div className="metric" key={metric.label} title={metricDescriptions[metric.label]}>
            <span>{metric.label}</span>
            <strong className={tone}>{formatMetric(metric)}</strong>
            {metricDescriptions[metric.label] ? <small>{metricDescriptions[metric.label]}</small> : null}
          </div>
        );
      })}
    </section>
  );
}

function DataStatus({ loading, through }: { loading: boolean; through: string | null }) {
  return (
    <div className={`statusPill ${loading ? "loading" : ""}`} aria-live="polite">
      <span>{loading ? "Updating" : "Data through"}</span>
      <strong>{loading ? "Syncing…" : displayDate(through)}</strong>
    </div>
  );
}

function PeriodContext({ fromDate, date }: { fromDate: string; date: string }) {
  return (
    <div className="periodContext">
      <span>Balances are as of <strong>{displayDate(date)}</strong>.</span>
      <span>Flows, income, and P/L cover <strong>{displayDate(fromDate)}–{displayDate(date)}</strong>.</span>
    </div>
  );
}

function Panel({
  title,
  icon,
  action,
  children
}: {
  title: string;
  icon?: React.ReactNode;
  action?: React.ReactNode;
  children: React.ReactNode;
}) {
  return (
    <section className="panel">
      <div className="panelTitle">
        <div className="panelTitleMain">
          {icon}
          <h2>{title}</h2>
        </div>
        {action ? <div className="panelAction">{action}</div> : null}
      </div>
      {children}
    </section>
  );
}

function EmptyState({ label }: { label: string }) {
  return <div className="emptyState">{label}</div>;
}

function chartTooltip() {
  return {
    contentStyle: {
      background: "#081018",
      border: "1px solid rgba(45,242,201,0.25)",
      color: "#e8fff8"
    },
    formatter: (value: unknown) => formatValue(value)
  };
}

function pivotSeries(
  rows: Record<string, string | number | null>[],
  keyColumn: string,
  valueColumn: string
): { data: Record<string, string | number | null>[]; keys: string[] } {
  const byDate = new Map<string, Record<string, string | number | null>>();
  const keys = new Set<string>();
  for (const row of rows) {
    const date = String(row.Date ?? "");
    const key = String(row[keyColumn] ?? "");
    if (!date || !key) {
      continue;
    }
    keys.add(key);
    const target = byDate.get(date) ?? { Date: date };
    target[key] = row[valueColumn];
    byDate.set(date, target);
  }
  return {
    data: [...byDate.values()].sort((a, b) => String(a.Date).localeCompare(String(b.Date))),
    keys: [...keys].sort()
  };
}

function BreakdownDonut({ items, emptyLabel }: { items: BreakdownItem[]; emptyLabel: string }) {
  if (!items.length) {
    return <EmptyState label={emptyLabel} />;
  }
  const total = items.reduce((sum, item) => sum + Math.abs(item.value), 0);
  return (
    <div className="compositionWrap">
      <ResponsiveContainer height={280}>
        <PieChart>
          <Pie data={items} dataKey="value" nameKey="label" innerRadius={74} outerRadius={108} paddingAngle={2}>
            {items.map((item, index) => (
              <Cell key={item.label} fill={accentColors[index % accentColors.length]} />
            ))}
          </Pie>
          <Tooltip {...chartTooltip()} />
        </PieChart>
      </ResponsiveContainer>
      <div className="legendList">
        {items.slice(0, 9).map((item, index) => (
          <div key={item.label}>
            <i style={{ background: accentColors[index % accentColors.length] }} />
            <span>{friendlyLabel(item.label)}</span>
            <strong>{formatValue(item.value)} <small>{total ? `${((Math.abs(item.value) / total) * 100).toFixed(1)}%` : ""}</small></strong>
          </div>
        ))}
      </div>
    </div>
  );
}

function InvestmentCharts({
  payload,
  compositionControl,
  showQuantity
}: {
  payload: InvestmentPayload;
  compositionControl?: React.ReactNode;
  showQuantity: boolean;
}) {
  return (
    <div className="chartGrid">
      <Panel title="Performance" icon={<Activity size={18} />}>
        <TimeChart
          data={payload.history}
          emptyLabel="No performance history."
          height={340}
          series={[
            { key: "Market Value", color: "#2df2c9", kind: "area" },
            { key: "Invested Capital", color: "#b7ff5a", dashed: true }
          ]}
        />
      </Panel>

      <Panel title={payload.composition.kind === "metadata" ? "Asset details" : "Composition"} icon={<Layers3 size={18} />} action={compositionControl}>
        <Composition payload={payload.composition} />
      </Panel>

      <Panel title="Profit/Loss" icon={<Gauge size={18} />}>
        <TimeChart
          data={payload.history}
          emptyLabel="No profit/loss history."
          height={260}
          series={[{ key: "Profit/Loss", color: "#b7ff5a", kind: "area" }]}
        />
      </Panel>

      {showQuantity ? (
        <Panel title="Quantity" icon={<RefreshCcw size={18} />}>
          <TimeChart
            data={payload.history}
            emptyLabel="No quantity history."
            height={260}
            series={[{ key: "Quantity", color: "#7aa7ff" }]}
          />
        </Panel>
      ) : null}
    </div>
  );
}

function Composition({ payload }: { payload: CompositionPayload }) {
  if (payload.kind === "metadata") {
    return (
      <div className="metadataGrid">
        {payload.items.map((item) => (
          <div key={item.label}>
            <span>{item.label}</span>
            <strong>{friendlyLabel(item.value)}</strong>
          </div>
        ))}
      </div>
    );
  }
  if (payload.kind === "empty" || !payload.items.length) {
    return <EmptyState label="No active holdings." />;
  }
  const total = payload.items.reduce((sum, item) => sum + Math.abs(item.value), 0);
  return (
    <div className="compositionWrap">
      <ResponsiveContainer height={270}>
        <PieChart>
          <Pie data={payload.items} dataKey="value" nameKey="label" innerRadius={70} outerRadius={105} paddingAngle={2}>
            {payload.items.map((item, index) => (
              <Cell key={item.label} fill={accentColors[index % accentColors.length]} />
            ))}
          </Pie>
          <Tooltip {...chartTooltip()} />
        </PieChart>
      </ResponsiveContainer>
      <div className="legendList">
        {payload.items.slice(0, 8).map((item, index) => (
          <div key={item.label}>
            <i style={{ background: accentColors[index % accentColors.length] }} />
            <span>{friendlyLabel(item.label)}</span>
            <strong>{formatValue(item.value)} <small>{total ? `${((Math.abs(item.value) / total) * 100).toFixed(1)}%` : ""}</small></strong>
          </div>
        ))}
      </div>
    </div>
  );
}

function TableCell({ value, column }: { value: unknown; column: string }) {
  if (value === null || value === undefined || value === "") {
    return <span className="emptyValue">—</span>;
  }
  if (column === "TX Hash" && typeof value === "string" && value.startsWith("0x")) {
    return (
      <a className="hashLink" href={`https://arbiscan.io/tx/${value}`} target="_blank" rel="noreferrer" title={value}>
        {`${value.slice(0, 8)}…${value.slice(-6)}`}
      </a>
    );
  }
  return <>{formatTableValue(value, column)}</>;
}

function DataTable({ table, emptyLabel }: { table: TablePayload; emptyLabel: string }) {
  if (!table.rows.length) {
    return <EmptyState label={emptyLabel} />;
  }
  return (
    <div className="tableWrap">
      <table>
        <thead>
          <tr>
            {table.columns.map((column) => (
              <th key={column}>{column}</th>
            ))}
          </tr>
        </thead>
        <tbody>
          {table.rows.map((row, index) => (
            <tr key={index}>
              {table.columns.map((column) => (
                <td data-label={column} key={column}><TableCell value={row[column]} column={column} /></td>
              ))}
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

type OverviewData = {
  stocks: InvestmentPayload;
  nexo: InvestmentPayload;
  arbitrum: ArbitrumPayload;
  realEstate: RealEstatePayload;
};

function lastNumeric(rows: Record<string, string | number | null>[], key: string): number {
  for (let index = rows.length - 1; index >= 0; index -= 1) {
    const value = rows[index]?.[key];
    if (typeof value === "number") {
      return value;
    }
  }
  return 0;
}

function OverviewDashboard({
  date,
  fromDate,
  period,
  onAsOfDateChange,
  onFromDateChange,
  onPeriodChange,
  onStartDateChange,
  onNavigate
}: {
  date: string;
  fromDate: string;
  period: PeriodKey;
  onAsOfDateChange: (date: string) => void;
  onFromDateChange: (date: string) => void;
  onPeriodChange: (period: Exclude<PeriodKey, "custom">) => void;
  onStartDateChange: (date: string | null) => void;
  onNavigate: (tab: TabKey) => void;
}) {
  const [payload, setPayload] = useState<OverviewData | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");

  useEffect(() => {
    let activeRequest = true;
    setLoading(true);
    setError("");
    Promise.all([
      fetchStocks(new URLSearchParams({ date, fromDate, dimension: "group", selection: ALL, composition: "name" })),
      fetchNexo(new URLSearchParams({ date, fromDate, coin: ALL })),
      fetchArbitrum(new URLSearchParams({ date, fromDate, asset: ALL, composition: "name", currency: "EUR" })),
      fetchRealEstate(new URLSearchParams({ date, fromDate }))
    ])
      .then(([stocks, nexo, arbitrum, realEstate]) => {
        if (activeRequest) {
          setPayload({ stocks, nexo, arbitrum, realEstate });
        }
      })
      .catch((reason: Error) => activeRequest && setError(reason.message))
      .finally(() => activeRequest && setLoading(false));
    return () => {
      activeRequest = false;
    };
  }, [date, fromDate]);

  useEffect(() => {
    if (!payload) {
      onStartDateChange(null);
      return;
    }
    const starts = [payload.stocks.startDate, payload.nexo.startDate, payload.arbitrum.startDate, payload.realEstate.startDate]
      .filter(Boolean)
      .sort();
    onStartDateChange(starts[0] ?? null);
  }, [payload, onStartDateChange]);

  const stockValue = payload ? metricValue(payload.stocks.metrics, "Current Value") : 0;
  const nexoValue = payload ? metricValue(payload.nexo.metrics, "Current Value") : 0;
  const arbitrumValue = payload ? metricValue(payload.arbitrum.metrics, "Current Value") : 0;
  const propertyValue = payload ? metricValue(payload.realEstate.metrics, "Property Value") : 0;
  const grossMortgage = payload
    ? payload.realEstate.mortgages.rows
      .filter((row) => Number(row["Outstanding Principal"]) > 0)
      .reduce((sum, row) => sum + Number(row["Outstanding Principal"]), 0)
    : 0;
  const loanReceivable = payload
    ? payload.realEstate.mortgages.rows
      .filter((row) => Number(row["Outstanding Principal"]) < 0)
      .reduce((sum, row) => sum + Math.abs(Number(row["Outstanding Principal"])), 0)
    : 0;
  const propertyEquity = payload ? metricValue(payload.realEstate.metrics, "Estimated Equity") : 0;
  const periodProfitLoss = payload
    ? metricValue(payload.stocks.metrics, "Net P/L")
      + metricValue(payload.nexo.metrics, "Net P/L")
      + metricValue(payload.arbitrum.metrics, "Net P/L")
      + lastNumeric(payload.realEstate.profitLoss, "Total P/L")
    : 0;
  const netWorth = stockValue + nexoValue + arbitrumValue + propertyEquity;
  const openingNetWorth = payload
    ? lastNumeric(payload.stocks.history.slice(0, 1), "Market Value")
      + lastNumeric(payload.nexo.history.slice(0, 1), "Market Value")
      + lastNumeric(payload.arbitrum.history.slice(0, 1), "Market Value")
      + lastNumeric(payload.realEstate.valueEquity.slice(0, 1), "Estimated Equity")
    : 0;
  const overviewMetrics: Metric[] = [
    { label: "Net worth", value: netWorth, display: "EUR " },
    { label: "Investable assets", value: stockValue + nexoValue + arbitrumValue, display: "EUR " },
    { label: "Property equity", value: propertyEquity, display: "EUR " },
    { label: "Liabilities", value: grossMortgage, display: "EUR " },
    { label: "Opening net worth", value: openingNetWorth, display: "EUR " },
    { label: "Period P/L", value: periodProfitLoss, display: "EUR " }
  ];
  const allocation: BreakdownItem[] = [
    { label: "Stocks", value: stockValue },
    { label: "NEXO", value: nexoValue },
    { label: "Arbitrum", value: arbitrumValue },
    { label: "Real Estate equity", value: propertyEquity }
  ].filter((item) => item.value > 0);
  const sourceCards = payload ? [
    { key: "stocks" as const, label: "Stocks", value: stockValue, pnl: metricValue(payload.stocks.metrics, "Net P/L"), through: latestDate(payload.stocks.history) },
    { key: "nexo" as const, label: "NEXO", value: nexoValue, pnl: metricValue(payload.nexo.metrics, "Net P/L"), through: latestDate(payload.nexo.history) },
    { key: "arbitrum" as const, label: "Arbitrum", value: arbitrumValue, pnl: metricValue(payload.arbitrum.metrics, "Net P/L"), through: latestDate(payload.arbitrum.history) },
    { key: "realEstate" as const, label: "Real Estate", value: propertyEquity, pnl: lastNumeric(payload.realEstate.profitLoss, "Total P/L"), through: latestDate(payload.realEstate.valueEquity) }
  ] : [];
  const dates = sourceCards.map((source) => source.through).filter((value): value is string => Boolean(value)).sort();

  return (
    <div className="workspace">
      <div className="workspaceHeader">
        <div>
          <p className="eyebrow">Whole portfolio</p>
          <h1>Overview</h1>
        </div>
        <DataStatus loading={loading} through={dates[0] ?? null} />
      </div>
      <section className="periodCard"><PeriodSelector value={period} onChange={onPeriodChange} /></section>
      <section className="filterRail overviewRail">
        <DateField label="From" value={fromDate} max={date} onChange={onFromDateChange} />
        <DateField label="To" value={date} max={todayIso()} onChange={onAsOfDateChange} />
      </section>
      <PeriodContext fromDate={fromDate} date={date} />
      {error ? <div className="warning">Could not update the overview: {error}</div> : null}
      {payload ? (
        <div className={`contentState ${loading ? "isLoading" : ""}`} aria-busy={loading}>
          <MetricStrip metrics={overviewMetrics} />
          <div className="overviewGrid">
            <Panel title="Net-worth allocation" icon={<Layers3 size={18} />}>
              <BreakdownDonut items={allocation} emptyLabel="No portfolio value available." />
            </Panel>
            <Panel title="Assets and liabilities" icon={<Gauge size={18} />}>
              <div className="balanceBridge">
                <div><span>Total assets</span><strong>EUR {formatValue(stockValue + nexoValue + arbitrumValue + propertyValue + loanReceivable)}</strong></div>
                <div><span>Mortgage liabilities</span><strong>EUR {formatValue(grossMortgage)}</strong></div>
                <div className="balanceTotal"><span>Net worth</span><strong>EUR {formatValue(netWorth)}</strong></div>
              </div>
            </Panel>
          </div>
          <Panel title="Accounts" icon={<WalletCards size={18} />}>
            <div className="accountGrid">
              {sourceCards.map((source) => (
                <button key={source.key} type="button" onClick={() => onNavigate(source.key)}>
                  <span>{source.label}</span>
                  <strong>EUR {formatValue(source.value)}</strong>
                  <small className={source.pnl < 0 ? "negative" : "positive"}>
                    Period P/L {source.pnl < 0 ? "−" : "+"}EUR {formatValue(Math.abs(source.pnl))}
                  </small>
                  <small>Data through {displayDate(source.through)}</small>
                </button>
              ))}
            </div>
          </Panel>
        </div>
      ) : <EmptyState label="Loading the whole portfolio." />}
    </div>
  );
}

function ArbitrumDashboard({
  options,
  date,
  fromDate,
  period,
  onAsOfDateChange,
  onFromDateChange,
  onPeriodChange,
  onStartDateChange
}: {
  options: OptionsPayload;
  date: string;
  fromDate: string;
  period: PeriodKey;
  onAsOfDateChange: (date: string) => void;
  onFromDateChange: (date: string) => void;
  onPeriodChange: (period: Exclude<PeriodKey, "custom">) => void;
  onStartDateChange: (date: string | null) => void;
}) {
  const [asset, setAsset] = useState(ALL);
  const [currency, setCurrency] = useState("EUR");
  const [payload, setPayload] = useState<ArbitrumPayload | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");

  const assetOptions = useMemo(() => withAll(options.arbitrum), [options.arbitrum]);

  useEffect(() => {
    setAsset(optionValue(assetOptions, asset));
  }, [assetOptions, asset]);

  useEffect(() => {
    setCurrency(optionValue(currencies, currency));
  }, [currency]);

  useEffect(() => {
    const params = new URLSearchParams({
      date,
      fromDate,
      asset,
      composition: "name",
      currency
    });
    let activeRequest = true;
    setLoading(true);
    setError("");
    fetchArbitrum(params)
      .then((nextPayload) => {
        if (activeRequest) {
          setPayload(nextPayload);
        }
      })
      .catch((reason: Error) => {
        if (activeRequest) {
          setError(reason.message);
        }
      })
      .finally(() => {
        if (activeRequest) {
          setLoading(false);
        }
      });

    return () => {
      activeRequest = false;
    };
  }, [date, fromDate, asset, currency]);

  useEffect(() => {
    onStartDateChange(null);
  }, [asset, onStartDateChange]);

  useEffect(() => {
    if (payload?.startDate) {
      onStartDateChange(payload.startDate);
    }
  }, [payload?.startDate, onStartDateChange]);

  const openingValue = payload?.history.find((row) => typeof row["Market Value"] === "number")?.["Market Value"];
  const openingCurrency = payload?.metrics[0]?.display.match(/^[A-Z]{3}\s/)?.[0] ?? `${currency} `;
  const metrics = payload && typeof openingValue === "number"
    ? [payload.metrics[0], { label: "Opening Value", value: openingValue, display: openingCurrency }, ...payload.metrics.slice(1)]
    : (payload?.metrics ?? []);
  const through = payload ? latestDate(payload.history) : null;

  return (
    <div className="workspace">
      <div className="workspaceHeader">
        <div>
          <p className="eyebrow">On-chain portfolio</p>
          <h1>{payload?.title ?? "Arbitrum Portfolio"}</h1>
        </div>
        <DataStatus loading={loading} through={through} />
      </div>

      <section className="periodCard">
        <PeriodSelector value={period} onChange={onPeriodChange} />
      </section>

      <section className="filterRail arbitrumRail">
        <DateField label="From" value={fromDate} max={date} onChange={onFromDateChange} />
        <DateField label="To" value={date} max={todayIso()} onChange={onAsOfDateChange} />
        <SelectField label="Asset" value={asset} options={assetOptions} onChange={setAsset} />
        <SegmentedControl label="Reporting currency" value={currency} options={currencies} onChange={setCurrency} />
      </section>

      <PeriodContext fromDate={fromDate} date={date} />

      {error ? <div className="warning">{error}</div> : null}
      {(payload?.warnings ?? []).map((warning) => (
        <div className="warning" key={warning}>{warning}</div>
      ))}

      {payload ? (
        <div className={`contentState ${loading ? "isLoading" : ""}`} aria-busy={loading}>
          <MetricStrip metrics={metrics} />
          <div className="chartGrid">
            <Panel title="Portfolio Value" icon={<Activity size={18} />}>
              <TimeChart
                data={payload.history}
                emptyLabel="No value history."
                series={[
                  { key: "Market Value", color: "#2df2c9", kind: "area" },
                  { key: "Invested Capital", color: "#b7ff5a", dashed: true }
                ]}
              />
            </Panel>

            {asset === ALL ? (
              <Panel title="Composition" icon={<Layers3 size={18} />}>
                <Composition payload={payload.composition} />
              </Panel>
            ) : (
              <Panel title="Position details" icon={<Layers3 size={18} />}>
                <DataTable table={payload.sources} emptyLabel="No position details." />
              </Panel>
            )}

            <Panel title="Profit/Loss" icon={<Gauge size={18} />}>
              <TimeChart
                data={payload.history}
                emptyLabel="No profit/loss history."
                height={260}
                series={[{ key: "Profit/Loss", color: "#b7ff5a", kind: "area" }]}
              />
            </Panel>

            <Panel title={asset !== ALL ? "Quantity" : "Transaction Activity"} icon={<RefreshCcw size={18} />}>
              <TimeChart
                data={asset !== ALL ? payload.history : payload.transactionHistory}
                emptyLabel={asset !== ALL ? "No quantity history." : "No transaction activity."}
                height={260}
                series={[
                  {
                    key: asset !== ALL ? "Quantity" : "Tx Count",
                    color: "#7aa7ff",
                    kind: asset !== ALL ? "line" : "bar"
                  }
                ]}
              />
            </Panel>
          </div>
          <div className="tableStack">
            <Panel title="Latest transactions · all time">
              <DataTable table={payload.transactions} emptyLabel="No transactions." />
            </Panel>
          </div>
        </div>
      ) : (
        <EmptyState label="Loading Arbitrum portfolio." />
      )}
    </div>
  );
}

type ChartSeries = {
  key: string;
  color: string;
  kind?: "area" | "bar" | "line";
  dashed?: boolean;
  prominent?: boolean;
};

function TimeChart({
  data,
  series,
  emptyLabel,
  height = 300
}: {
  data: Record<string, string | number | null>[];
  series: ChartSeries[];
  emptyLabel: string;
  height?: number;
}) {
  if (!data.length) {
    return <EmptyState label={emptyLabel} />;
  }
  return (
    <ResponsiveContainer height={height}>
      <ComposedChart data={data}>
        <CartesianGrid stroke="rgba(255,255,255,0.07)" vertical={false} />
        <XAxis dataKey="Date" minTickGap={32} tick={{ fill: "#7d8b9f", fontSize: 11 }} tickLine={false} axisLine={false} />
        <YAxis tick={{ fill: "#7d8b9f", fontSize: 11 }} tickFormatter={formatValue} tickLine={false} axisLine={false} width={86} />
        <Tooltip {...chartTooltip()} />
        <Legend iconType="line" wrapperStyle={{ color: "#9eacb9", fontSize: 11, paddingTop: 10 }} />
        {series.map(({ key, color, kind = "line", dashed, prominent }) =>
          kind === "area" ? (
            <Area dataKey={key} fill={color} fillOpacity={0.18} key={key} stroke={color} strokeWidth={2.5} />
          ) : kind === "bar" ? (
            <Bar dataKey={key} fill={color} key={key} radius={[5, 5, 0, 0]} />
          ) : (
            <Line
              dataKey={key}
              dot={false}
              key={key}
              stroke={color}
              strokeDasharray={dashed ? "5 5" : undefined}
              strokeWidth={prominent ? 3 : 2.5}
            />
          )
        )}
      </ComposedChart>
    </ResponsiveContainer>
  );
}

function InvestmentDashboard({
  kind,
  options,
  date,
  fromDate,
  period,
  onAsOfDateChange,
  onFromDateChange,
  onPeriodChange,
  onStartDateChange
}: {
  kind: "stocks" | "nexo";
  options: OptionsPayload;
  date: string;
  fromDate: string;
  period: PeriodKey;
  onAsOfDateChange: (date: string) => void;
  onFromDateChange: (date: string) => void;
  onPeriodChange: (period: Exclude<PeriodKey, "custom">) => void;
  onStartDateChange: (date: string | null) => void;
}) {
  const assets = options[kind];
  const isStocks = kind === "stocks";
  const [dimension, setDimension] = useState("group");
  const [selection, setSelection] = useState(ALL);
  const [composition, setComposition] = useState("name");
  const [payload, setPayload] = useState<InvestmentPayload | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");

  const selectionOptions = useMemo(
    () => {
      const values = isStocks ? groupsForMode(assets, dimension) : [...assets].sort((left, right) => left.label.localeCompare(right.label));
      return isStocks && dimension === "name" ? values : withAll(values);
    },
    [isStocks, assets, dimension]
  );
  const compositionOptions = stockCompositions.filter((option) => option.value !== dimension);
  const compositionControl =
    isStocks && dimension !== "name" ? (
      <SelectField
        label="Composition"
        value={composition}
        options={compositionOptions}
        onChange={setComposition}
      />
    ) : null;

  useEffect(() => {
    setSelection(optionValue(selectionOptions, selection));
  }, [selectionOptions, selection]);

  useEffect(() => {
    setComposition(optionValue(compositionOptions, composition));
  }, [compositionOptions, composition]);

  useEffect(() => {
    const params = isStocks
      ? new URLSearchParams({ date, fromDate, dimension, selection, composition })
      : new URLSearchParams({ date, fromDate, coin: selection });
    let activeRequest = true;
    setLoading(true);
    setError("");
    const load = kind === "stocks" ? fetchStocks : fetchNexo;
    load(params)
      .then((nextPayload) => activeRequest && setPayload(nextPayload))
      .catch((reason: Error) => activeRequest && setError(reason.message))
      .finally(() => activeRequest && setLoading(false));
    return () => {
      activeRequest = false;
    };
  }, [kind, isStocks, date, fromDate, dimension, selection, composition]);

  useEffect(() => {
    onStartDateChange(null);
  }, [kind, dimension, selection, onStartDateChange]);

  useEffect(() => {
    if (payload?.startDate) {
      onStartDateChange(payload.startDate);
    }
  }, [payload?.startDate, onStartDateChange]);

  const metrics = payload ? investmentMetrics(payload.metrics, kind, payload.history) : [];
  const through = payload ? latestDate(payload.history) : null;
  const selectionLabel = !isStocks
    ? "Asset"
    : ({ group: "Asset group", region: "Region", provider: "Provider", name: "Asset" }[dimension] ?? "Selection");

  return (
    <div className="workspace">
      <div className="workspaceHeader">
        <div>
          <p className="eyebrow">{kind === "stocks" ? "Securities" : "Crypto credit"}</p>
          <h1>{payload?.title ?? (kind === "stocks" ? "Stocks" : "NEXO")}</h1>
        </div>
        <DataStatus loading={loading} through={through} />
      </div>

      <section className="periodCard">
        <PeriodSelector value={period} onChange={onPeriodChange} />
      </section>

      <section className="filterRail compactRail">
        <DateField label="From" value={fromDate} max={date} onChange={onFromDateChange} />
        <DateField label="To" value={date} max={todayIso()} onChange={onAsOfDateChange} />
        {isStocks ? (
          <SelectField label="Filter by" value={dimension} options={stockDimensions} onChange={setDimension} />
        ) : null}
        <SelectField label={selectionLabel} value={selection} options={selectionOptions} onChange={setSelection} />
      </section>

      <PeriodContext fromDate={fromDate} date={date} />

      {error ? <div className="warning">{error}</div> : null}
      {payload ? (
        <div className={`contentState ${loading ? "isLoading" : ""}`} aria-busy={loading}>
          <MetricStrip metrics={metrics} />
          <InvestmentCharts payload={payload} compositionControl={compositionControl} showQuantity={selection !== ALL} />
          <Panel title="Latest transactions · all time">
            <DataTable
              table={payload.transactions}
              emptyLabel="No transactions for this selection."
            />
          </Panel>
        </div>
      ) : (
        <EmptyState label="Loading dashboard data." />
      )}
    </div>
  );
}

function RealEstateDashboard({
  date,
  fromDate,
  period,
  onAsOfDateChange,
  onFromDateChange,
  onPeriodChange,
  onStartDateChange
}: {
  date: string;
  fromDate: string;
  period: PeriodKey;
  onAsOfDateChange: (date: string) => void;
  onFromDateChange: (date: string) => void;
  onPeriodChange: (period: Exclude<PeriodKey, "custom">) => void;
  onStartDateChange: (date: string | null) => void;
}) {
  const [payload, setPayload] = useState<RealEstatePayload | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");
  const receivableRows = payload?.mortgages.rows.filter((row) => Number(row["Outstanding Principal"]) < 0) ?? [];
  const receivableIds = new Set(receivableRows.map((row) => String(row["Mortgage ID"] ?? "")));
  const mortgageRows = payload?.mortgages.rows.filter((row) => Number(row["Outstanding Principal"]) >= 0) ?? [];
  const rawMortgageSeries = payload
    ? pivotSeries(payload.mortgageBalances, "Mortgage ID", "Outstanding Principal")
    : { data: [], keys: [] };
  const mortgageSeries = {
    data: rawMortgageSeries.data,
    keys: rawMortgageSeries.keys.filter((key) => !receivableIds.has(key))
  };

  useEffect(() => {
    const params = new URLSearchParams({ date, fromDate });
    let activeRequest = true;
    setLoading(true);
    setError("");
    fetchRealEstate(params)
      .then((nextPayload) => activeRequest && setPayload(nextPayload))
      .catch((reason: Error) => activeRequest && setError(reason.message))
      .finally(() => activeRequest && setLoading(false));
    return () => {
      activeRequest = false;
    };
  }, [date, fromDate]);

  useEffect(() => {
    onStartDateChange(null);
  }, [onStartDateChange]);

  useEffect(() => {
    if (payload?.startDate) {
      onStartDateChange(payload.startDate);
    }
  }, [payload?.startDate, onStartDateChange]);

  const propertyValue = payload ? metricValue(payload.metrics, "Property Value") : 0;
  const grossMortgageValue = mortgageRows.reduce((sum, row) => sum + Number(row["Outstanding Principal"] ?? 0), 0);
  const loanReceivableValue = receivableRows.reduce((sum, row) => sum + Math.abs(Number(row["Outstanding Principal"] ?? 0)), 0);
  const realEstateMetrics = payload ? [
    payload.metrics.find((metric) => metric.label === "Property Value"),
    { label: "Gross mortgage debt", value: grossMortgageValue, display: "EUR " },
    ...(loanReceivableValue ? [{ label: "Loan receivable", value: loanReceivableValue, display: "EUR " }] : []),
    payload.metrics.find((metric) => metric.label === "Estimated Equity"),
    payload.metrics.find((metric) => metric.label === "Net Cash Out")
      ? { ...payload.metrics.find((metric) => metric.label === "Net Cash Out")!, label: "Period net cash flow" }
      : undefined,
    { label: "LTV", value: propertyValue ? (grossMortgageValue / propertyValue) * 100 : 0, display: "%" }
  ].filter((metric): metric is Metric => Boolean(metric)) : [];
  const mortgageTable: TablePayload = payload ? { ...payload.mortgages, rows: mortgageRows } : { columns: [], rows: [] };
  const receivableTable: TablePayload = payload ? {
    columns: ["Loan ID", "Original Amount", "Interest Received", "Principal Repaid", "Balance Receivable"],
    rows: receivableRows.map((row) => ({
      "Loan ID": row["Mortgage ID"],
      "Original Amount": Math.abs(Number(row["Initial Principal"] ?? 0)),
      "Interest Received": Math.abs(Number(row["Interest Paid"] ?? 0)),
      "Principal Repaid": Math.abs(Number(row["Principal Repaid"] ?? 0)),
      "Balance Receivable": Math.abs(Number(row["Outstanding Principal"] ?? 0))
    }))
  } : { columns: [], rows: [] };
  const redirectedLoanInflows: Record<string, string | number | null>[] = payload?.recentOutflows.rows
    .filter((row) => Number(row.Amount) < 0)
    .map((row) => ({
      ...row,
      Type: String(row.Type ?? "Loan repayment").replace(/^Mortgage:/, "Loan repayment:")
    })) ?? [];
  const latestOutflows: TablePayload = payload ? flowTable({
    ...payload.recentOutflows,
    rows: payload.recentOutflows.rows.filter((row) => Number(row.Amount) >= 0)
  }) : { columns: [], rows: [] };
  const latestInflows: TablePayload = payload ? flowTable({
    ...payload.recentInflows,
    rows: [...payload.recentInflows.rows, ...redirectedLoanInflows]
      .sort((left, right) => String(right["Date"] ?? "").localeCompare(String(left["Date"] ?? "")))
      .slice(0, 5)
  }) : { columns: [], rows: [] };
  const through = payload ? latestDate(payload.valueEquity) : null;

  return (
    <div className="workspace">
      <div className="workspaceHeader">
        <div>
          <p className="eyebrow">Property ledger</p>
          <h1>Real Estate</h1>
        </div>
        <DataStatus loading={loading} through={through} />
      </div>

      <section className="periodCard">
        <PeriodSelector value={period} onChange={onPeriodChange} />
      </section>

      <section className="filterRail compactRail">
        <DateField label="From" value={fromDate} max={date} onChange={onFromDateChange} />
        <DateField label="To" value={date} max={todayIso()} onChange={onAsOfDateChange} />
      </section>

      <PeriodContext fromDate={fromDate} date={date} />

      {error ? <div className="warning">{error}</div> : null}

      {payload ? (
        <div className={`contentState ${loading ? "isLoading" : ""}`} aria-busy={loading}>
          <MetricStrip metrics={realEstateMetrics} />
          <div className="chartGrid">
            <Panel title="Value and Equity">
              <TimeChart
                data={payload.valueEquity}
                emptyLabel="No valuation data."
                height={330}
                series={[
                  { key: "Property Value", color: "#2df2c9" },
                  { key: "Outstanding Mortgage", color: "#ff63a5" },
                  { key: "Estimated Equity", color: "#b7ff5a", prominent: true }
                ]}
              />
            </Panel>
            <Panel title="Monthly cash flow">
              <TimeChart
                data={payload.cashflow}
                emptyLabel="No cashflow data."
                height={330}
                series={[
                  { key: "Inflows", color: "#2df2c9", kind: "bar" },
                  { key: "Home Costs", color: "#ff63a5", kind: "bar" },
                  { key: "Mortgage Interest", color: "#7aa7ff", kind: "bar" },
                  { key: "Mortgage Repayment", color: "#f6d45d", kind: "bar" }
                ]}
              />
            </Panel>
            <Panel title="P/L Breakdown">
              <TimeChart
                data={payload.profitLoss}
                emptyLabel="No equity/cashflow history."
                height={330}
                series={[
                  { key: "Estimated Equity", color: "#2df2c9" },
                  { key: "Cumulative Net Cash Flow", color: "#7aa7ff" },
                  { key: "Total P/L", color: "#b7ff5a", prominent: true }
                ]}
              />
            </Panel>
            <Panel title="Mortgage Balances">
              <TimeChart
                data={mortgageSeries.data}
                emptyLabel="No mortgage balance history."
                height={330}
                series={mortgageSeries.keys.map((key, index) => ({
                  key,
                  color: accentColors[index % accentColors.length],
                  prominent: key === "TOTAL"
                }))}
              />
            </Panel>
            <Panel title="Inflow Breakdown">
              <BreakdownDonut items={payload.inflows} emptyLabel="No inflow breakdown." />
            </Panel>
            <Panel title="Outflow Breakdown">
              <BreakdownDonut items={payload.outflows} emptyLabel="No outflow breakdown." />
            </Panel>
          </div>
          <div className="tableStack">
            <Panel title="Mortgage Summary">
              <DataTable table={mortgageTable} emptyLabel="No mortgage summary." />
            </Panel>
            {receivableRows.length ? (
              <Panel title="Offsetting loan receivable">
                <DataTable table={receivableTable} emptyLabel="No loan receivable." />
              </Panel>
            ) : null}
            <Panel title="Latest outflows">
              <DataTable table={latestOutflows} emptyLabel="No outflows." />
            </Panel>
            <Panel title="Latest inflows">
              <DataTable table={latestInflows} emptyLabel="No inflows." />
            </Panel>
          </div>
        </div>
      ) : (
        <EmptyState label="Loading dashboard data." />
      )}
    </div>
  );
}

const refreshOptions: { kind: RefreshKind; label: string }[] = [
  { kind: "prices", label: "Update market prices" },
  { kind: "transactions", label: "Import Getquin activity" },
  { kind: "crypto", label: "Update crypto data" },
  { kind: "all", label: "Update all data" }
];

function RefreshControls({
  job,
  onRefresh
}: {
  job: RefreshJob | null;
  onRefresh: (kind: RefreshKind) => void;
}) {
  const active = job?.status === "queued" || job?.status === "running";
  return (
    <section className="refreshControls">
      <span className="dataSectionLabel">Available updates</span>
      {refreshOptions.map((option) => (
        <button
          disabled={active}
          key={option.kind}
          onClick={() => onRefresh(option.kind)}
          type="button"
        >
          <RefreshCcw className={active ? "spinning" : ""} size={15} />
          <span>{option.label}</span>
        </button>
      ))}
      {job ? (
        <small className={`refreshStatus ${job.status}`}>
          {job.currentStep ?? job.error ?? job.status}
        </small>
      ) : null}
    </section>
  );
}

function DataManagement({
  open,
  job,
  onClose,
  onRefresh,
  onStop
}: {
  open: boolean;
  job: RefreshJob | null;
  onClose: () => void;
  onRefresh: (kind: RefreshKind) => void;
  onStop: () => void;
}) {
  if (!open) {
    return null;
  }
  return (
    <div className="modalBackdrop" role="presentation" onMouseDown={(event) => event.target === event.currentTarget && onClose()}>
      <section className="dataModal" role="dialog" aria-modal="true" aria-labelledby="data-management-title">
        <div className="dataModalHeader">
          <div>
            <p className="eyebrow">Maintenance</p>
            <h2 id="data-management-title">Data management</h2>
          </div>
          <button className="iconButton" type="button" aria-label="Close data management" onClick={onClose}><X size={18} /></button>
        </div>
        <p className="dataModalIntro">These actions update the external portfolio workspace. Only one update can run at a time.</p>
        <RefreshControls job={job} onRefresh={onRefresh} />
        <div className="dangerZone">
          <span className="dataSectionLabel">Dashboard process</span>
          <button className="serverStop" type="button" onClick={onStop}>
            <Power size={17} />
            <span>Stop dashboard</span>
          </button>
        </div>
      </section>
    </div>
  );
}

export default function App() {
  const [active, setActive] = useState<TabKey>("overview");
  const [date, setDate] = useState(todayIso());
  const [customFromDate, setCustomFromDate] = useState(() => {
    const today = parseIsoDate(todayIso());
    return isoDate(today.year, 1, 1);
  });
  const [period, setPeriod] = useState<PeriodKey>("ytd");
  const [activeStartDate, setActiveStartDate] = useState<string | null>(null);
  const [options, setOptions] = useState<OptionsPayload | null>(null);
  const [error, setError] = useState("");
  const [stopMessage, setStopMessage] = useState("");
  const [refreshJob, setRefreshJob] = useState<RefreshJob | null>(null);
  const [refreshRevision, setRefreshRevision] = useState(0);
  const [mobileNavOpen, setMobileNavOpen] = useState(false);
  const [dataManagementOpen, setDataManagementOpen] = useState(false);
  const [privacyMode, setPrivacyMode] = useState(false);

  useEffect(() => {
    fetchOptions().then(setOptions).catch((reason: Error) => setError(reason.message));
  }, []);

  useEffect(() => {
    setActiveStartDate(null);
  }, [active]);

  useEffect(() => {
    if (!refreshJob || !["queued", "running"].includes(refreshJob.status)) {
      return;
    }
    const timer = window.setInterval(() => {
      fetchRefreshJob(refreshJob.id)
        .then((updated) => {
          setRefreshJob(updated);
          if (updated.status === "succeeded") {
            setRefreshRevision((value) => value + 1);
            fetchOptions().then(setOptions).catch((reason: Error) => setError(reason.message));
          }
        })
        .catch((reason: Error) => setError(reason.message));
    }, 1000);
    return () => window.clearInterval(timer);
  }, [refreshJob]);

  const fromDate = useMemo(() => {
    if (period === "custom") {
      return clampFromDate(customFromDate, date, activeStartDate);
    }
    return periodStartDate(period, date, activeStartDate) ?? customFromDate;
  }, [activeStartDate, customFromDate, date, period]);

  useEffect(() => {
    if (period !== "custom") {
      return;
    }

    const clamped = clampFromDate(customFromDate, date, activeStartDate);
    if (clamped !== customFromDate) {
      setCustomFromDate(clamped);
    }
  }, [activeStartDate, customFromDate, date, period]);

  const handleAsOfDateChange = useCallback((value: string) => {
    if (value) {
      setDate(minIso(value, todayIso()));
    }
  }, []);

  const handleFromDateChange = useCallback(
    (value: string) => {
      if (!value) {
        return;
      }
      setPeriod("custom");
      setCustomFromDate(clampFromDate(value, date, activeStartDate));
    },
    [activeStartDate, date]
  );

  const handlePeriodChange = useCallback(
    (value: Exclude<PeriodKey, "custom">) => {
      setPeriod(value);
      const resolved = periodStartDate(value, date, activeStartDate);
      if (resolved) {
        setCustomFromDate(resolved);
      }
    },
    [activeStartDate, date]
  );

  function handleStopServer() {
    const confirmed = window.confirm("Stop this dashboard? It will remain unavailable until it is started again.");
    if (!confirmed) {
      return;
    }
    stopServer()
      .then(() => setStopMessage("Dashboard stop requested. This page will stop updating until the dashboard is started again."))
      .catch((reason: Error) => setStopMessage(reason.message));
  }

  function handleRefresh(kind: RefreshKind) {
    setError("");
    startRefresh(kind).then(setRefreshJob).catch((reason: Error) => setError(reason.message));
  }

  return (
    <main className={`appShell ${privacyMode ? "privacyMode" : ""}`}>
      <aside className="sidebar">
        <div className="sidebarHeader">
          <div className="brand">
            <span />
            <div>
              <strong>Portfolio Terminal</strong>
              <small>Private ledger</small>
            </div>
          </div>
          <button className="mobileMenuButton" type="button" aria-label="Toggle navigation" aria-expanded={mobileNavOpen} onClick={() => setMobileNavOpen((value) => !value)}>
            {mobileNavOpen ? <X size={20} /> : <Menu size={20} />}
          </button>
        </div>
        <div className={`navDrawer ${mobileNavOpen ? "open" : ""}`}>
          <nav>
            {tabs.map((tab) => {
              const Icon = tab.icon;
              return (
                <button className={active === tab.key ? "active" : ""} key={tab.key} onClick={() => { setActive(tab.key); setMobileNavOpen(false); }}>
                  <Icon size={18} />
                  <span>{tab.label}</span>
                </button>
              );
            })}
          </nav>
          <div className="sidebarUtilities">
            <button type="button" onClick={() => { setDataManagementOpen(true); setMobileNavOpen(false); }}>
              <Database size={17} />
              <span>Data management</span>
              {refreshJob?.status === "running" || refreshJob?.status === "queued" ? <i className="statusDot" /> : null}
            </button>
            <button type="button" onClick={() => setPrivacyMode((value) => !value)}>
              {privacyMode ? <Eye size={17} /> : <EyeOff size={17} />}
              <span>{privacyMode ? "Show balances" : "Hide balances"}</span>
            </button>
          </div>
        </div>
      </aside>
      <section className="mainStage">
        <div className="ambientGrid" />
        {error ? <div className="warning">{error}</div> : null}
        {stopMessage ? <div className="warning">{stopMessage}</div> : null}
        {options ? (
          <div key={`${active}-${refreshRevision}`}>
              {active === "overview" ? (
                <OverviewDashboard
                  date={date}
                  fromDate={fromDate}
                  period={period}
                  onAsOfDateChange={handleAsOfDateChange}
                  onFromDateChange={handleFromDateChange}
                  onPeriodChange={handlePeriodChange}
                  onStartDateChange={setActiveStartDate}
                  onNavigate={setActive}
                />
              ) : null}
              {active === "stocks" ? (
                <InvestmentDashboard
                  kind="stocks"
                  options={options}
                  date={date}
                  fromDate={fromDate}
                  period={period}
                  onAsOfDateChange={handleAsOfDateChange}
                  onFromDateChange={handleFromDateChange}
                  onPeriodChange={handlePeriodChange}
                  onStartDateChange={setActiveStartDate}
                />
              ) : null}
              {active === "nexo" ? (
                <InvestmentDashboard
                  kind="nexo"
                  options={options}
                  date={date}
                  fromDate={fromDate}
                  period={period}
                  onAsOfDateChange={handleAsOfDateChange}
                  onFromDateChange={handleFromDateChange}
                  onPeriodChange={handlePeriodChange}
                  onStartDateChange={setActiveStartDate}
                />
              ) : null}
              {active === "arbitrum" ? (
                <ArbitrumDashboard
                  options={options}
                  date={date}
                  fromDate={fromDate}
                  period={period}
                  onAsOfDateChange={handleAsOfDateChange}
                  onFromDateChange={handleFromDateChange}
                  onPeriodChange={handlePeriodChange}
                  onStartDateChange={setActiveStartDate}
                />
              ) : null}
              {active === "realEstate" ? (
                <RealEstateDashboard
                  date={date}
                  fromDate={fromDate}
                  period={period}
                  onAsOfDateChange={handleAsOfDateChange}
                  onFromDateChange={handleFromDateChange}
                  onPeriodChange={handlePeriodChange}
                  onStartDateChange={setActiveStartDate}
                />
              ) : null}
          </div>
        ) : (
          <EmptyState label="Connecting to backend." />
        )}
      </section>
      <DataManagement
        open={dataManagementOpen}
        job={refreshJob}
        onClose={() => setDataManagementOpen(false)}
        onRefresh={handleRefresh}
        onStop={handleStopServer}
      />
    </main>
  );
}
