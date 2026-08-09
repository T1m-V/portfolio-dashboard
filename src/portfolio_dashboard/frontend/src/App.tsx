import {
  Area,
  Bar,
  CartesianGrid,
  Cell,
  ComposedChart,
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
  Gauge,
  Layers3,
  Power,
  RefreshCcw,
  ShieldCheck,
  WalletCards
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

type TabKey = "stocks" | "nexo" | "arbitrum" | "realEstate";
type PeriodKey = "mtd" | "ytd" | "1y" | "3y" | "5y" | "sinceStart" | "custom";

const tabs: { key: TabKey; label: string; icon: typeof WalletCards }[] = [
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
  { label: "Single Asset", value: "name" }
];
const stockCompositions: Option[] = [
  { label: "Asset Name", value: "name" },
  { label: "Asset Group", value: "group" },
  { label: "Region", value: "region" },
  { label: "Provider", value: "provider" }
];
const arbitrumCompositions: Option[] = [
  { label: "Asset Name", value: "name" },
  { label: "Valuation Route", value: "route" },
  { label: "Exposure Type", value: "exposure" }
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
  { key: "mtd", label: "MtD" },
  { key: "ytd", label: "YtD" },
  { key: "1y", label: "1y" },
  { key: "3y", label: "3y" },
  { key: "5y", label: "5y" },
  { key: "sinceStart", label: "Since start" }
];

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
  const currencyPrefix = metric.display.match(/^[A-Z]{3}\s/)?.[0] ?? "";
  return `${currencyPrefix}${formatValue(metric.value)}`;
}

function formatTableValue(value: unknown, column: string): string {
  if (typeof value !== "number") {
    return String(value ?? "");
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
    return options;
  }
  const values = new Set<string>();
  for (const option of options) {
    const value = option[mode as keyof Option];
    if (typeof value === "string" && value) {
      values.add(value);
    }
  }
  return [...values].sort().map((value) => ({ label: value, value }));
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
        const negative = metric.value < 0;
        return (
          <div className="metric" key={metric.label}>
            <span>{metric.label}</span>
            <strong className={negative ? "negative" : "positive"}>{formatMetric(metric)}</strong>
          </div>
        );
      })}
    </section>
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
            <span>{item.label}</span>
            <strong>{formatValue(item.value)}</strong>
          </div>
        ))}
      </div>
    </div>
  );
}

function InvestmentCharts({
  payload,
  compositionControl
}: {
  payload: InvestmentPayload;
  compositionControl?: React.ReactNode;
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

      <Panel title="Composition" icon={<Layers3 size={18} />} action={compositionControl}>
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

      <Panel title="Quantity" icon={<RefreshCcw size={18} />}>
        <TimeChart
          data={payload.history}
          emptyLabel="No quantity history."
          height={260}
          series={[{ key: "Quantity", color: "#7aa7ff" }]}
        />
      </Panel>
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
            <strong>{item.value}</strong>
          </div>
        ))}
      </div>
    );
  }
  if (payload.kind === "empty" || !payload.items.length) {
    return <EmptyState label="No active holdings." />;
  }
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
            <span>{item.label}</span>
            <strong>{formatValue(item.value)}</strong>
          </div>
        ))}
      </div>
    </div>
  );
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
                <td key={column}>{formatTableValue(row[column], column)}</td>
              ))}
            </tr>
          ))}
        </tbody>
      </table>
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
  const [composition, setComposition] = useState("name");
  const [currency, setCurrency] = useState("EUR");
  const [payload, setPayload] = useState<ArbitrumPayload | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");

  const assetOptions = useMemo(() => withAll(options.arbitrum), [options.arbitrum]);

  useEffect(() => {
    setAsset(optionValue(assetOptions, asset));
  }, [assetOptions, asset]);

  useEffect(() => {
    setComposition(optionValue(arbitrumCompositions, composition));
  }, [composition]);

  useEffect(() => {
    setCurrency(optionValue(currencies, currency));
  }, [currency]);

  useEffect(() => {
    const params = new URLSearchParams({
      date,
      fromDate,
      asset,
      composition,
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
  }, [date, fromDate, asset, composition, currency]);

  useEffect(() => {
    onStartDateChange(null);
  }, [asset, onStartDateChange]);

  useEffect(() => {
    if (payload?.startDate) {
      onStartDateChange(payload.startDate);
    }
  }, [payload?.startDate, onStartDateChange]);

  return (
    <div className="workspace">
      <div className="workspaceHeader">
        <div>
          <p className="eyebrow">On-chain portfolio</p>
          <h1>{payload?.title ?? "Arbitrum Portfolio"}</h1>
        </div>
        <div className="statusPill">{loading ? "Syncing" : "Live"}</div>
      </div>

      <section className="periodCard">
        <PeriodSelector value={period} onChange={onPeriodChange} />
      </section>

      <section className="filterRail arbitrumRail">
        <DateField label="From" value={fromDate} max={date} onChange={onFromDateChange} />
        <DateField label="To date" value={date} onChange={onAsOfDateChange} />
        <SelectField label="Asset" value={asset} options={assetOptions} onChange={setAsset} />
        <SelectField label="Composition" value={composition} options={arbitrumCompositions} onChange={setComposition} />
        <SegmentedControl label="Currency" value={currency} options={currencies} onChange={setCurrency} />
      </section>

      {error ? <div className="warning">{error}</div> : null}
      {(payload?.warnings ?? []).map((warning) => (
        <div className="warning" key={warning}>{warning}</div>
      ))}

      {payload ? (
        <>
          <MetricStrip metrics={payload.metrics} />
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

            <Panel title="Composition" icon={<Layers3 size={18} />}>
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
            {asset !== ALL ? (
              <Panel title="Sources" icon={<Layers3 size={18} />}>
                <DataTable table={payload.sources} emptyLabel="No source breakdown." />
              </Panel>
            ) : null}
            <Panel title="Latest Transactions">
              <DataTable table={payload.transactions} emptyLabel="No transactions." />
            </Panel>
          </div>
        </>
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
        <XAxis dataKey="Date" tick={{ fill: "#7d8b9f", fontSize: 11 }} tickLine={false} axisLine={false} />
        <YAxis tick={{ fill: "#7d8b9f", fontSize: 11 }} tickFormatter={formatValue} tickLine={false} axisLine={false} width={86} />
        <Tooltip {...chartTooltip()} />
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
    () => withAll(isStocks ? groupsForMode(assets, dimension) : assets),
    [isStocks, assets, dimension]
  );
  const compositionOptions = stockCompositions.filter((option) => option.value !== dimension);
  const compositionControl =
    isStocks && (dimension !== "name" || selection === ALL) ? (
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

  return (
    <div className="workspace">
      <div className="workspaceHeader">
        <div>
          <p className="eyebrow">{kind === "stocks" ? "Securities" : "Crypto credit"}</p>
          <h1>{payload?.title ?? (kind === "stocks" ? "Stocks" : "NEXO")}</h1>
        </div>
        <div className="statusPill">{loading ? "Syncing" : "Live"}</div>
      </div>

      <section className="periodCard">
        <PeriodSelector value={period} onChange={onPeriodChange} />
      </section>

      <section className="filterRail compactRail">
        <DateField label="From" value={fromDate} max={date} onChange={onFromDateChange} />
        <DateField label="To date" value={date} onChange={onAsOfDateChange} />
        {isStocks ? (
          <SelectField label="Analysis" value={dimension} options={stockDimensions} onChange={setDimension} />
        ) : null}
        <SelectField label="Selection" value={selection} options={selectionOptions} onChange={setSelection} />
      </section>

      {error ? <div className="warning">{error}</div> : null}
      {payload ? (
        <>
          <MetricStrip metrics={payload.metrics} />
          <InvestmentCharts payload={payload} compositionControl={compositionControl} />
          <Panel title="Recent Transactions">
            <DataTable
              table={payload.transactions}
              emptyLabel="No transactions for this selection."
            />
          </Panel>
        </>
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
  const mortgageSeries = payload
    ? pivotSeries(payload.mortgageBalances, "Mortgage ID", "Outstanding Principal")
    : { data: [], keys: [] };

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

  return (
    <div className="workspace">
      <div className="workspaceHeader">
        <div>
          <p className="eyebrow">Property ledger</p>
          <h1>Real Estate</h1>
        </div>
        <div className="statusPill">{loading ? "Syncing" : "Live"}</div>
      </div>

      <section className="periodCard">
        <PeriodSelector value={period} onChange={onPeriodChange} />
      </section>

      <section className="filterRail compactRail">
        <DateField label="From" value={fromDate} max={date} onChange={onFromDateChange} />
        <DateField label="To date" value={date} onChange={onAsOfDateChange} />
      </section>

      {error ? <div className="warning">{error}</div> : null}

      {payload ? (
        <>
          <MetricStrip metrics={payload.metrics} />
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
            <Panel title="Monthly Cashflow">
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
              <DataTable table={payload.mortgages} emptyLabel="No mortgage summary." />
            </Panel>
            <Panel title="Recent Outflows">
              <DataTable table={payload.recentOutflows} emptyLabel="No outflows." />
            </Panel>
            <Panel title="Recent Inflows">
              <DataTable table={payload.recentInflows} emptyLabel="No inflows." />
            </Panel>
          </div>
        </>
      ) : (
        <EmptyState label="Loading dashboard data." />
      )}
    </div>
  );
}

const refreshOptions: { kind: RefreshKind; label: string }[] = [
  { kind: "prices", label: "Refresh prices" },
  { kind: "transactions", label: "Refresh Getquin" },
  { kind: "crypto", label: "Refresh crypto" },
  { kind: "all", label: "Refresh all" }
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
      <span className="sidebarLabel">Data loaders</span>
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

export default function App() {
  const [active, setActive] = useState<TabKey>("stocks");
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
      setDate(value);
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
    const confirmed = window.confirm("Stop the dashboard backend for this checkout?");
    if (!confirmed) {
      return;
    }
    stopServer()
      .then(() => setStopMessage("Backend stop requested. The frontend page can stay open, but API data will stop refreshing until the backend is restarted."))
      .catch((reason: Error) => setStopMessage(reason.message));
  }

  function handleRefresh(kind: RefreshKind) {
    setError("");
    startRefresh(kind).then(setRefreshJob).catch((reason: Error) => setError(reason.message));
  }

  return (
    <main className="appShell">
      <aside className="sidebar">
        <div className="brand">
          <span />
          <div>
            <strong>Portfolio Terminal</strong>
            <small>Private ledger</small>
          </div>
        </div>
        <nav>
          {tabs.map((tab) => {
            const Icon = tab.icon;
            return (
              <button className={active === tab.key ? "active" : ""} key={tab.key} onClick={() => setActive(tab.key)}>
                <Icon size={18} />
                <span>{tab.label}</span>
              </button>
            );
          })}
        </nav>
        <RefreshControls job={refreshJob} onRefresh={handleRefresh} />
        <button className="serverStop" type="button" onClick={handleStopServer}>
          <Power size={17} />
          <span>Stop Backend</span>
        </button>
      </aside>
      <section className="mainStage">
        <div className="ambientGrid" />
        {error ? <div className="warning">{error}</div> : null}
        {stopMessage ? <div className="warning">{stopMessage}</div> : null}
        {options ? (
          <div key={`${active}-${refreshRevision}`}>
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
    </main>
  );
}
