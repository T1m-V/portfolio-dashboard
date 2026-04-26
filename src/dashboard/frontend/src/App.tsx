import { AnimatePresence, motion } from "framer-motion";
import {
  Area,
  AreaChart,
  Bar,
  BarChart,
  CartesianGrid,
  Cell,
  Line,
  LineChart,
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
  RefreshCcw,
  WalletCards
} from "lucide-react";
import { useEffect, useMemo, useState } from "react";
import type React from "react";
import { fetchNexo, fetchOptions, fetchRealEstate, fetchStocks } from "./api";
import type {
  CompositionPayload,
  BreakdownItem,
  InvestmentPayload,
  Metric,
  Option,
  OptionsPayload,
  RealEstatePayload,
  TablePayload
} from "./types";

type TabKey = "stocks" | "nexo" | "realEstate";

const tabs: { key: TabKey; label: string; icon: typeof WalletCards }[] = [
  { key: "stocks", label: "Stocks", icon: WalletCards },
  { key: "nexo", label: "NEXO", icon: Coins },
  { key: "realEstate", label: "Real Estate", icon: Building2 }
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
  "tax",
  "usd equivalent",
  "value"
];

function todayIso(): string {
  return new Date().toISOString().slice(0, 10);
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

function groupsForMode(options: Option[], mode: string): Option[] {
  if (mode === "full") {
    return [];
  }
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

function DateField({ value, onChange }: { value: string; onChange: (value: string) => void }) {
  return (
    <label className="field">
      <span>As-of</span>
      <input type="date" value={value} onChange={(event) => onChange(event.target.value)} />
    </label>
  );
}

function MetricStrip({ metrics }: { metrics: Metric[] }) {
  if (!metrics.length) {
    return <div className="emptyState">No metrics for this selection.</div>;
  }
  return (
    <section className="metricStrip">
      {metrics.map((metric, index) => {
        const negative = metric.value < 0;
        return (
          <motion.div
            className="metric"
            key={metric.label}
            initial={{ opacity: 0, y: 12 }}
            animate={{ opacity: 1, y: 0 }}
            transition={{ delay: index * 0.04 }}
            whileHover={{ y: -3 }}
          >
            <span>{metric.label}</span>
            <strong className={negative ? "negative" : "positive"}>{formatMetric(metric)}</strong>
          </motion.div>
        );
      })}
    </section>
  );
}

function Panel({
  title,
  icon,
  children
}: {
  title: string;
  icon?: React.ReactNode;
  children: React.ReactNode;
}) {
  return (
    <section className="panel">
      <div className="panelTitle">
        {icon}
        <h2>{title}</h2>
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

function InvestmentCharts({ payload }: { payload: InvestmentPayload }) {
  const history = payload.history;
  return (
    <div className="chartGrid">
      <Panel title="Performance" icon={<Activity size={18} />}>
        {history.length ? (
          <ResponsiveContainer height={340}>
            <AreaChart data={history}>
              <defs>
                <linearGradient id="marketValue" x1="0" x2="0" y1="0" y2="1">
                  <stop offset="5%" stopColor="#2df2c9" stopOpacity={0.45} />
                  <stop offset="95%" stopColor="#2df2c9" stopOpacity={0.02} />
                </linearGradient>
              </defs>
              <CartesianGrid stroke="rgba(255,255,255,0.07)" vertical={false} />
              <XAxis dataKey="Date" tick={{ fill: "#7d8b9f", fontSize: 11 }} tickLine={false} axisLine={false} />
              <YAxis tick={{ fill: "#7d8b9f", fontSize: 11 }} tickFormatter={formatValue} tickLine={false} axisLine={false} width={86} />
              <Tooltip {...chartTooltip()} />
              <Area dataKey="Market Value" stroke="#2df2c9" fill="url(#marketValue)" strokeWidth={2.5} />
              <Line dataKey="Invested Capital" stroke="#b7ff5a" strokeDasharray="5 5" dot={false} strokeWidth={2} />
            </AreaChart>
          </ResponsiveContainer>
        ) : (
          <EmptyState label="No performance history." />
        )}
      </Panel>

      <Panel title="Composition" icon={<Layers3 size={18} />}>
        <Composition payload={payload.composition} />
      </Panel>

      <Panel title="Profit/Loss" icon={<Gauge size={18} />}>
        {history.length ? (
          <ResponsiveContainer height={260}>
            <AreaChart data={history}>
              <defs>
                <linearGradient id="profitLoss" x1="0" x2="0" y1="0" y2="1">
                  <stop offset="5%" stopColor="#b7ff5a" stopOpacity={0.38} />
                  <stop offset="95%" stopColor="#b7ff5a" stopOpacity={0.03} />
                </linearGradient>
              </defs>
              <CartesianGrid stroke="rgba(255,255,255,0.07)" vertical={false} />
              <XAxis dataKey="Date" tick={{ fill: "#7d8b9f", fontSize: 11 }} tickLine={false} axisLine={false} />
              <YAxis tick={{ fill: "#7d8b9f", fontSize: 11 }} tickFormatter={formatValue} tickLine={false} axisLine={false} width={86} />
              <Tooltip {...chartTooltip()} />
              <Area dataKey="Profit/Loss" stroke="#b7ff5a" fill="url(#profitLoss)" strokeWidth={2.5} />
            </AreaChart>
          </ResponsiveContainer>
        ) : (
          <EmptyState label="No profit/loss history." />
        )}
      </Panel>

      <Panel title="Quantity" icon={<RefreshCcw size={18} />}>
        {history.length ? (
          <ResponsiveContainer height={260}>
            <LineChart data={history}>
              <CartesianGrid stroke="rgba(255,255,255,0.07)" vertical={false} />
              <XAxis dataKey="Date" tick={{ fill: "#7d8b9f", fontSize: 11 }} tickLine={false} axisLine={false} />
              <YAxis tick={{ fill: "#7d8b9f", fontSize: 11 }} tickFormatter={formatNumber} tickLine={false} axisLine={false} />
              <Tooltip {...chartTooltip()} />
              <Line dataKey="Quantity" stroke="#7aa7ff" dot={false} strokeWidth={2.5} />
            </LineChart>
          </ResponsiveContainer>
        ) : (
          <EmptyState label="No quantity history." />
        )}
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

function InvestmentDashboard({
  kind,
  options,
  date,
  setDate
}: {
  kind: "stocks" | "nexo";
  options: OptionsPayload;
  date: string;
  setDate: (date: string) => void;
}) {
  const optionSet = options[kind];
  const [mode, setMode] = useState("full");
  const [selection, setSelection] = useState("");
  const [composition, setComposition] = useState("name");
  const [payload, setPayload] = useState<InvestmentPayload | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");

  const selectionOptions = useMemo(() => groupsForMode(optionSet.assets, mode), [optionSet.assets, mode]);
  const compositionOptions = optionSet.compositionModes.filter((option) => option.value !== mode);

  useEffect(() => {
    setSelection(optionValue(selectionOptions, selection));
  }, [selectionOptions, selection]);

  useEffect(() => {
    setComposition(optionValue(compositionOptions, composition));
  }, [compositionOptions, composition]);

  useEffect(() => {
    const params = new URLSearchParams({ date, mode, selection, composition });
    setLoading(true);
    setError("");
    const load = kind === "stocks" ? fetchStocks : fetchNexo;
    load(params)
      .then(setPayload)
      .catch((reason: Error) => setError(reason.message))
      .finally(() => setLoading(false));
  }, [kind, date, mode, selection, composition]);

  return (
    <motion.div className="workspace" initial={{ opacity: 0, y: 12 }} animate={{ opacity: 1, y: 0 }}>
      <div className="workspaceHeader">
        <div>
          <p className="eyebrow">{kind === "stocks" ? "Securities" : "Crypto credit"}</p>
          <h1>{payload?.title ?? (kind === "stocks" ? "Stocks" : "NEXO")}</h1>
        </div>
        <div className="statusPill">{loading ? "Syncing" : "Live"}</div>
      </div>

      <section className="filterRail">
        <DateField value={date} onChange={setDate} />
        <SelectField label="Analysis" value={mode} options={optionSet.analysisModes} onChange={setMode} />
        <SelectField label="Selection" value={selection} options={selectionOptions} disabled={mode === "full"} onChange={setSelection} />
        <SelectField label="Composition" value={composition} options={compositionOptions} disabled={mode === "name"} onChange={setComposition} />
      </section>

      {error ? <div className="warning">{error}</div> : null}
      {payload ? (
        <>
          <MetricStrip metrics={payload.summary.metrics} />
          <InvestmentCharts payload={payload} />
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
    </motion.div>
  );
}

function RealEstateDashboard({
  options,
  date,
  setDate
}: {
  options: OptionsPayload;
  date: string;
  setDate: (date: string) => void;
}) {
  const [asset, setAsset] = useState("ALL");
  const [outflowLimit, setOutflowLimit] = useState("5");
  const [inflowLimit, setInflowLimit] = useState("5");
  const [payload, setPayload] = useState<RealEstatePayload | null>(null);
  const [loading, setLoading] = useState(false);
  const rowLimitOptions = ["5", "10", "25", "50", "100", "ALL"].map((value) => ({ label: value, value }));
  const mortgageSeries = payload
    ? pivotSeries(payload.mortgageBalance, "Mortgage ID", "Outstanding Principal")
    : { data: [], keys: [] };

  useEffect(() => {
    const params = new URLSearchParams({ date, asset, outflowLimit, inflowLimit });
    setLoading(true);
    fetchRealEstate(params)
      .then(setPayload)
      .finally(() => setLoading(false));
  }, [date, asset, outflowLimit, inflowLimit]);

  return (
    <motion.div className="workspace" initial={{ opacity: 0, y: 12 }} animate={{ opacity: 1, y: 0 }}>
      <div className="workspaceHeader">
        <div>
          <p className="eyebrow">Property ledger</p>
          <h1>{payload?.title ?? "Real Estate"}</h1>
        </div>
        <div className="statusPill">{loading ? "Syncing" : "Live"}</div>
      </div>

      <section className="filterRail">
        <DateField value={date} onChange={setDate} />
        <SelectField label="Asset" value={asset} options={options.realEstate.assets} onChange={setAsset} />
        <SelectField label="Outflows" value={outflowLimit} options={rowLimitOptions} onChange={setOutflowLimit} />
        <SelectField label="Inflows" value={inflowLimit} options={rowLimitOptions} onChange={setInflowLimit} />
      </section>

      {(payload?.warnings ?? []).map((warning) => (
        <div className="warning" key={warning}>{warning}</div>
      ))}

      {payload ? (
        <>
          <MetricStrip metrics={payload.summary.metrics} />
          <div className="chartGrid">
            <Panel title="Value and Equity">
              {payload.valueEquity.length ? (
                <ResponsiveContainer height={330}>
                  <LineChart data={payload.valueEquity}>
                    <CartesianGrid stroke="rgba(255,255,255,0.07)" vertical={false} />
                    <XAxis dataKey="Date" tick={{ fill: "#7d8b9f", fontSize: 11 }} tickLine={false} axisLine={false} />
                    <YAxis tick={{ fill: "#7d8b9f", fontSize: 11 }} tickFormatter={formatValue} tickLine={false} axisLine={false} width={86} />
                    <Tooltip {...chartTooltip()} />
                    <Line dataKey="Property Value" stroke="#2df2c9" dot={false} strokeWidth={2.5} />
                    <Line dataKey="Outstanding Mortgage" stroke="#ff63a5" dot={false} strokeWidth={2.5} />
                    <Line dataKey="Estimated Equity" stroke="#b7ff5a" dot={false} strokeWidth={3} />
                  </LineChart>
                </ResponsiveContainer>
              ) : (
                <EmptyState label="No valuation data." />
              )}
            </Panel>
            <Panel title="Monthly Cashflow">
              {payload.cashflow.length ? (
                <ResponsiveContainer height={330}>
                  <BarChart data={payload.cashflow}>
                    <CartesianGrid stroke="rgba(255,255,255,0.07)" vertical={false} />
                    <XAxis dataKey="Date" tick={{ fill: "#7d8b9f", fontSize: 11 }} tickLine={false} axisLine={false} />
                    <YAxis tick={{ fill: "#7d8b9f", fontSize: 11 }} tickFormatter={formatValue} tickLine={false} axisLine={false} width={86} />
                    <Tooltip {...chartTooltip()} />
                    <Bar dataKey="Inflows" fill="#2df2c9" radius={[5, 5, 0, 0]} />
                    <Bar dataKey="Home Costs" fill="#ff63a5" radius={[5, 5, 0, 0]} />
                    <Bar dataKey="Mortgage Interest" fill="#7aa7ff" radius={[5, 5, 0, 0]} />
                    <Bar dataKey="Mortgage Repayment" fill="#f6d45d" radius={[5, 5, 0, 0]} />
                  </BarChart>
                </ResponsiveContainer>
              ) : (
                <EmptyState label="No cashflow data." />
              )}
            </Panel>
            <Panel title="P/L Breakdown">
              {payload.plBreakdown.length ? (
                <ResponsiveContainer height={330}>
                  <LineChart data={payload.plBreakdown}>
                    <CartesianGrid stroke="rgba(255,255,255,0.07)" vertical={false} />
                    <XAxis dataKey="Date" tick={{ fill: "#7d8b9f", fontSize: 11 }} tickLine={false} axisLine={false} />
                    <YAxis tick={{ fill: "#7d8b9f", fontSize: 11 }} tickFormatter={formatValue} tickLine={false} axisLine={false} width={86} />
                    <Tooltip {...chartTooltip()} />
                    <Line dataKey="Estimated Equity" stroke="#2df2c9" dot={false} strokeWidth={2.5} />
                    <Line dataKey="Cumulative Net Cash Flow" stroke="#7aa7ff" dot={false} strokeWidth={2.5} />
                    <Line dataKey="Total P/L" stroke="#b7ff5a" dot={false} strokeWidth={3} />
                  </LineChart>
                </ResponsiveContainer>
              ) : (
                <EmptyState label="No equity/cashflow history." />
              )}
            </Panel>
            <Panel title="Mortgage Balances">
              {mortgageSeries.data.length ? (
                <ResponsiveContainer height={330}>
                  <LineChart data={mortgageSeries.data}>
                    <CartesianGrid stroke="rgba(255,255,255,0.07)" vertical={false} />
                    <XAxis dataKey="Date" tick={{ fill: "#7d8b9f", fontSize: 11 }} tickLine={false} axisLine={false} />
                    <YAxis tick={{ fill: "#7d8b9f", fontSize: 11 }} tickFormatter={formatValue} tickLine={false} axisLine={false} width={86} />
                    <Tooltip {...chartTooltip()} />
                    {mortgageSeries.keys.map((key, index) => (
                      <Line
                        dataKey={key}
                        dot={false}
                        key={key}
                        stroke={accentColors[index % accentColors.length]}
                        strokeWidth={key === "TOTAL" ? 3 : 2}
                      />
                    ))}
                  </LineChart>
                </ResponsiveContainer>
              ) : (
                <EmptyState label="No mortgage balance history." />
              )}
            </Panel>
            <Panel title="Inflow Breakdown">
              <BreakdownDonut items={payload.inflowBreakdown} emptyLabel="No inflow breakdown." />
            </Panel>
            <Panel title="Outflow Breakdown">
              <BreakdownDonut items={payload.outflowBreakdown} emptyLabel="No outflow breakdown." />
            </Panel>
          </div>
          <div className="tableStack">
            <Panel title="Mortgage Summary">
              <DataTable table={payload.mortgageSummary} emptyLabel="No mortgage summary." />
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
    </motion.div>
  );
}

export default function App() {
  const [active, setActive] = useState<TabKey>("stocks");
  const [date, setDate] = useState(todayIso());
  const [options, setOptions] = useState<OptionsPayload | null>(null);
  const [error, setError] = useState("");

  useEffect(() => {
    fetchOptions().then(setOptions).catch((reason: Error) => setError(reason.message));
  }, []);

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
      </aside>
      <section className="mainStage">
        <div className="ambientGrid" />
        {error ? <div className="warning">{error}</div> : null}
        {options ? (
          <AnimatePresence mode="wait">
            <motion.div key={active} initial={{ opacity: 0, scale: 0.985 }} animate={{ opacity: 1, scale: 1 }} exit={{ opacity: 0, scale: 0.985 }} transition={{ duration: 0.18 }}>
              {active === "stocks" ? <InvestmentDashboard kind="stocks" options={options} date={date} setDate={setDate} /> : null}
              {active === "nexo" ? <InvestmentDashboard kind="nexo" options={options} date={date} setDate={setDate} /> : null}
              {active === "realEstate" ? <RealEstateDashboard options={options} date={date} setDate={setDate} /> : null}
            </motion.div>
          </AnimatePresence>
        ) : (
          <EmptyState label="Connecting to backend." />
        )}
      </section>
    </main>
  );
}
