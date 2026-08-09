from __future__ import annotations

from typing import Any

import pandas as pd
from portfolio_core import active_context, get_forex_rate
from portfolio_crypto_data.nexo_dashboard import (
    get_nexo_start_date,
    list_nexo_coins,
    load_and_process_nexo_data,
    load_recent_nexo_transactions,
)
from portfolio_market_data.dashboard_data import (
    get_stock_start_date,
    load_recent_stock_transactions,
    load_stock_history,
)

from portfolio_dashboard.arbitrum import (
    ArbitrumArtifacts,
    latest_as_of,
    load_arbitrum_artifacts,
    load_arbitrum_assets,
    select,
    selection_key,
    through_date,
)
from portfolio_dashboard.real_estate import (
    RealEstateData,
    load_real_estate_data,
    monthly_cashflow,
    mortgage_balances,
    mortgage_summary,
    period_net_cash_out,
    recent_cashflows,
    snapshot_metrics,
    value_equity,
)

ALL = "ALL"
PAGE_SIZE = 5
ARBITRUM_CHAIN = "arbitrum"


def _json_value(value: Any) -> Any:
    if pd.isna(value):
        return None
    if isinstance(value, pd.Timestamp):
        return value.strftime("%Y-%m-%d")
    return value


def records(frame: pd.DataFrame) -> list[dict[str, Any]]:
    return [
        {key: _json_value(value) for key, value in row.items()} for row in frame.to_dict("records")
    ]


def table(frame: pd.DataFrame, columns: list[str] | None = None) -> dict[str, Any]:
    visible = columns or list(frame.columns)
    visible = [column for column in visible if column in frame.columns]
    return {"columns": visible, "rows": records(frame[visible])}


def currency(value: float, unit: str = "EUR") -> str:
    decimals = 0 if abs(value) > 100 else 2
    return f"{unit} {value:,.{decimals}f}"


def _period(frame: pd.DataFrame, from_date: str, through_date: str) -> pd.DataFrame:
    if frame.empty:
        return frame.copy()
    return frame[frame["Date"].between(pd.Timestamp(from_date), pd.Timestamp(through_date))].copy()


def _optional_frame(load, *args, **kwargs) -> pd.DataFrame:
    try:
        return load(*args, **kwargs)
    except FileNotFoundError, pd.errors.EmptyDataError:
        return pd.DataFrame()


def build_options_payload() -> dict[str, list[dict[str, str]]]:
    context = active_context()
    stocks = [
        {
            "label": info.get("name", isin),
            "value": isin,
            "group": info["group"],
            "region": info["region"],
            "provider": info["provider"],
        }
        for isin, info in context.stock_metadata().items()
    ]
    metadata = context.currency_metadata()
    nexo = [
        {"label": metadata.get(coin, {}).get("name", coin), "value": coin}
        for coin in list_nexo_coins()
    ]
    assets = load_arbitrum_assets(ARBITRUM_CHAIN)
    arbitrum = (
        [
            {"label": row["Label"], "value": row["Value"]}
            for row in assets.sort_values("Label").to_dict("records")
        ]
        if not assets.empty
        else []
    )
    return {"stocks": stocks, "nexo": nexo, "arbitrum": arbitrum}


def _stock_isins(dimension: str, selection: str) -> list[str]:
    metadata = active_context().stock_metadata()
    if selection == ALL:
        return list(metadata)
    if dimension == "name":
        return [selection]
    return [isin for isin, info in metadata.items() if info[dimension] == selection]


def _snapshot(frame: pd.DataFrame, target: str, *, before: bool = False) -> pd.DataFrame:
    if frame.empty:
        return frame.copy()
    date = pd.Timestamp(target)
    candidates = frame[frame["Date"] < date] if before else frame[frame["Date"] <= date]
    if candidates.empty:
        return candidates.copy()
    return candidates[candidates["Date"] == candidates["Date"].max()].copy()


def _investment_totals(frame: pd.DataFrame) -> tuple[float, float, float, float, float]:
    if frame.empty:
        return 0.0, 0.0, 0.0, 0.0, 0.0
    return tuple(
        float(frame[column].sum())
        for column in (
            "Market Value",
            "Principal Invested",
            "Cumulative Fees",
            "Cumulative Taxes",
            "Gross Dividends",
        )
    )


def _investment_metrics(
    frame: pd.DataFrame, from_date: str, selected_date: str
) -> list[dict[str, Any]]:
    current = _snapshot(frame, selected_date)
    if current.empty:
        return []
    baseline = _snapshot(frame, from_date, before=True)
    value, principal, fees, taxes, dividends = _investment_totals(current)
    old_value, old_principal, old_fees, old_taxes, old_dividends = _investment_totals(baseline)
    dividends -= old_dividends
    fees -= old_fees
    taxes -= old_taxes
    net_invested = principal - old_principal + fees + taxes - dividends
    profit_loss = value - old_value - net_invested
    values = (
        ("Current Value", value),
        ("Net P/L", profit_loss),
        ("Net Invested", net_invested),
        ("Dividends", dividends),
        ("Fees", fees),
        ("Taxes", taxes),
    )
    return [
        {"label": label, "value": number, "display": currency(number)} for label, number in values
    ]


def _investment_history(
    frame: pd.DataFrame, from_date: str, selected_date: str
) -> list[dict[str, Any]]:
    if frame.empty:
        return []
    history = frame[frame["Date"] <= pd.Timestamp(selected_date)].copy()
    history["Invested Capital"] = (
        history["Principal Invested"]
        + history["Cumulative Fees"]
        + history["Cumulative Taxes"]
        - history["Gross Dividends"]
    )
    history = (
        history.groupby("Date", as_index=False)[["Market Value", "Invested Capital", "Quantity"]]
        .sum()
        .sort_values("Date")
    )
    baseline = history[history["Date"] < pd.Timestamp(from_date)].tail(1)
    old_value = float(baseline["Market Value"].iloc[0]) if not baseline.empty else 0.0
    old_invested = float(baseline["Invested Capital"].iloc[0]) if not baseline.empty else 0.0
    history = _period(history, from_date, selected_date)
    history["Profit/Loss"] = (history["Market Value"] - old_value) - (
        history["Invested Capital"] - old_invested
    )
    return records(history)


def _stock_composition(
    snapshot: pd.DataFrame, dimension: str, selection: str, composition: str
) -> dict[str, Any]:
    metadata = active_context().stock_metadata()
    if dimension == "name" and selection != ALL:
        info = metadata[selection]
        return {
            "kind": "metadata",
            "items": [
                {"label": "Ticker", "value": info.get("ticker", "-")},
                {"label": "ISIN", "value": selection},
                {"label": "Region", "value": info["region"]},
                {"label": "Asset Group", "value": info["group"]},
                {"label": "Provider", "value": info["provider"]},
            ],
        }
    if snapshot.empty:
        return {"kind": "empty", "items": []}
    active = snapshot[snapshot["Quantity"] > 0.00001].copy()
    if active.empty:
        return {"kind": "empty", "items": []}
    active["label"] = active["ISIN"].map(lambda isin: metadata[isin][composition])
    items = active.groupby("label", as_index=False)["Market Value"].sum()
    return {"kind": "breakdown", "items": records(items.rename(columns={"Market Value": "value"}))}


def build_stock_payload(
    *,
    selected_date: str,
    from_date: str,
    dimension: str,
    selection: str,
    composition: str,
) -> dict[str, Any]:
    context = active_context()
    isins = _stock_isins(dimension, selection)
    frame = _optional_frame(
        load_stock_history, context=context, end_date=selected_date, isins=isins
    )
    transactions = _optional_frame(
        load_recent_stock_transactions,
        context=context,
        end_date=selected_date,
        isins=isins,
        limit=PAGE_SIZE,
    )
    if selection == ALL:
        title = "Stocks"
    elif dimension == "name":
        title = context.stock_metadata()[selection]["name"]
    else:
        title = selection
    return {
        "title": title,
        "startDate": get_stock_start_date(context=context, isins=isins) or selected_date,
        "metrics": _investment_metrics(frame, from_date, selected_date),
        "history": _investment_history(frame, from_date, selected_date),
        "composition": _stock_composition(
            _snapshot(frame, selected_date), dimension, selection, composition
        ),
        "transactions": table(
            transactions,
            ["Date", "Type", "Asset Name", "Quantity", "Price", "Currency", "Fees", "Taxes"],
        ),
    }


def _nexo_composition(snapshot: pd.DataFrame, coin: str) -> dict[str, Any]:
    if coin != ALL:
        info = active_context().currency_metadata().get(coin, {})
        return {
            "kind": "metadata",
            "items": [
                {"label": "Ticker", "value": info.get("ticker", "-")},
                {"label": "Symbol", "value": coin},
                {"label": "Name", "value": info.get("name", coin)},
                {"label": "Group", "value": info.get("group", "Unknown")},
                {"label": "Currency", "value": info.get("currency", "USD")},
            ],
        }
    if snapshot.empty:
        return {"kind": "empty", "items": []}
    active = snapshot[snapshot["Quantity"].abs() > 0.00001]
    if active.empty:
        return {"kind": "empty", "items": []}
    items = active.groupby("Asset Name", as_index=False)["Market Value"].sum()
    return {
        "kind": "breakdown",
        "items": records(items.rename(columns={"Asset Name": "label", "Market Value": "value"})),
    }


def build_nexo_payload(*, selected_date: str, from_date: str, coin: str) -> dict[str, Any]:
    coins = None if coin == ALL else [coin]
    frame = _optional_frame(load_and_process_nexo_data, end_date_str=selected_date, coins=coins)
    transactions = _optional_frame(
        load_recent_nexo_transactions,
        end_date_str=selected_date,
        coins=coins,
        limit=PAGE_SIZE,
    )
    if not transactions.empty:
        transactions = transactions.copy()
        transactions["Input"] = (
            transactions["Input Amount"].astype(str) + " " + transactions["Input Currency"]
        )
        transactions["Output"] = (
            transactions["Output Amount"].astype(str) + " " + transactions["Output Currency"]
        )
    title = (
        "NEXO"
        if coin == ALL
        else active_context().currency_metadata().get(coin, {}).get("name", coin)
    )
    return {
        "title": title,
        "startDate": get_nexo_start_date(coins=coins) or selected_date,
        "metrics": _investment_metrics(frame, from_date, selected_date),
        "history": _investment_history(frame, from_date, selected_date),
        "composition": _nexo_composition(_snapshot(frame, selected_date), coin),
        "transactions": table(
            transactions, ["Date", "Type", "Input", "Output", "USD Equivalent", "Details"]
        ),
    }


def _convert_from_eur(
    frame: pd.DataFrame, columns: list[str], unit: str, fallback_date: str
) -> pd.DataFrame:
    if frame.empty or unit == "EUR":
        return frame.copy()
    result = frame.copy()
    dates = result["Date"] if "Date" in result else pd.Series(fallback_date, index=result.index)
    day_keys = pd.to_datetime(dates).dt.strftime("%Y-%m-%d")
    rates = {
        day: float(
            get_forex_rate(
                currency="USD",
                date=day,
                prices_folder=active_context().paths.prices,
            )
        )
        for day in day_keys.unique()
    }
    for column in columns:
        result[column] = result[column] / day_keys.map(rates)
    return result


def _arbitrum_transactions(
    artifacts: ArbitrumArtifacts, asset: str, selected_date: str, limit: int | None
) -> pd.DataFrame:
    frame = artifacts.transactions.copy()
    if frame.empty:
        return frame
    if asset != ALL:
        key = selection_key(asset)
        frame = frame[frame["AssetKeys"].fillna("").str.split(";").map(lambda keys: key in keys)]
    frame = frame[frame["Date"].dt.normalize() <= pd.Timestamp(selected_date)].sort_values(
        "Date", ascending=False
    )
    if limit is not None:
        frame = frame.head(limit)
    frame = frame.copy()
    frame["Date"] = frame["Date"].dt.strftime("%Y-%m-%d %H:%M:%S")
    return frame


def _arbitrum_composition(
    artifacts: ArbitrumArtifacts,
    asset: str,
    selected_date: str,
    composition: str,
    unit: str,
) -> dict[str, Any]:
    frame = select(artifacts.composition, asset)
    frame = latest_as_of(frame[frame["CompositionMode"] == composition], selected_date)
    frame = _convert_from_eur(frame, ["ValueEUR"], unit, selected_date)
    if frame.empty:
        return {"kind": "empty", "items": []}
    items = (
        frame.groupby("Label", as_index=False)["ValueEUR"]
        .sum()
        .rename(columns={"Label": "label", "ValueEUR": "value"})
        .sort_values("value", ascending=False)
        .head(12)
    )
    items = items[items["value"].abs() > 0]
    return {"kind": "breakdown", "items": records(items)}


def build_arbitrum_payload(
    *,
    selected_date: str,
    from_date: str,
    asset: str,
    composition: str,
    currency_unit: str,
) -> dict[str, Any]:
    artifacts = load_arbitrum_artifacts(ARBITRUM_CHAIN)
    history = through_date(select(artifacts.timeseries, asset), selected_date)
    history = _convert_from_eur(
        history,
        ["MarketValueEUR", "PrincipalInvestedEUR", "ProfitLossEUR"],
        currency_unit,
        selected_date,
    ).rename(
        columns={
            "MarketValueEUR": "Market Value",
            "PrincipalInvestedEUR": "Invested Capital",
            "ProfitLossEUR": "Profit/Loss",
        }
    )
    history = history[["Date", "Market Value", "Invested Capital", "Profit/Loss", "Quantity"]]
    period_history = _period(history, from_date, selected_date)
    latest = latest_as_of(history, selected_date)
    current = latest.iloc[-1] if not latest.empty else {}
    transactions = _arbitrum_transactions(artifacts, asset, selected_date, None)
    metric_values = (
        ("Current Value", float(current.get("Market Value", 0))),
        ("Net P/L", float(current.get("Profit/Loss", 0))),
        ("Net Invested", float(current.get("Invested Capital", 0))),
        ("Transactions", len(transactions)),
    )
    metrics = [
        {
            "label": label,
            "value": value,
            "display": f"{value:,}" if label == "Transactions" else currency(value, currency_unit),
        }
        for label, value in metric_values
    ]
    transaction_history = _period(
        through_date(select(artifacts.timeseries, asset), selected_date), from_date, selected_date
    )[["Date", "TxCount"]].rename(columns={"TxCount": "Tx Count"})

    sources = select(artifacts.sources, asset) if asset != ALL else artifacts.sources.iloc[:0]
    sources = latest_as_of(sources, selected_date)
    sources = _convert_from_eur(
        sources,
        ["MarketValueEUR", "PrincipalInvestedEUR", "ProfitLossEUR"],
        currency_unit,
        selected_date,
    ).rename(
        columns={
            "MarketValueEUR": "Market Value",
            "PrincipalInvestedEUR": "Invested Capital",
            "ProfitLossEUR": "Profit/Loss",
            "ValuationRoute": "Valuation Route",
        }
    )
    if not sources.empty:
        sources = (
            sources.assign(_value=sources["Market Value"].abs())
            .sort_values("_value", ascending=False)
            .head(25)
        )

    return {
        "title": "Arbitrum" if asset == ALL else f"Arbitrum: {asset}",
        "startDate": (
            history["Date"].min().strftime("%Y-%m-%d") if not history.empty else selected_date
        ),
        "metrics": metrics,
        "history": records(period_history),
        "transactionHistory": records(transaction_history),
        "composition": _arbitrum_composition(
            artifacts, asset, selected_date, composition, currency_unit
        ),
        "sources": table(
            sources,
            [
                "Source",
                "Quantity",
                "Market Value",
                "Invested Capital",
                "Profit/Loss",
                "Valuation Route",
            ],
        ),
        "transactions": table(
            _arbitrum_transactions(artifacts, asset, selected_date, PAGE_SIZE),
            [
                "Date",
                "Type",
                "Token in",
                "Qty in",
                "Token out",
                "Qty out",
                "Fee",
                "Fee Token",
                "TX Hash",
            ],
        ),
        "warnings": artifacts.warnings,
    }


def _real_estate_breakdowns(data: RealEstateData) -> tuple[list[dict], list[dict]]:
    outflows: list[dict[str, str | float]] = []
    if not data.costs.empty:
        costs = data.costs.groupby("Cost Type", as_index=False)["Amount"].sum()
        for row in costs.to_dict("records"):
            outflows.append({"label": f"Cost: {row['Cost Type']}", "value": row["Amount"]})
    if not data.mortgages.empty:
        payments = data.mortgages[data.mortgages["Entry Type"] == "PAYMENT"]
        outflows.extend(
            [
                {"label": "Mortgage Interest", "value": float(payments["Interest Paid"].sum())},
                {"label": "Mortgage Repayment", "value": float(payments["Principal Repaid"].sum())},
            ]
        )
    inflows = (
        data.inflows.groupby("Inflow Type", as_index=False)["Amount"]
        .sum()
        .rename(columns={"Inflow Type": "label", "Amount": "value"})
        if not data.inflows.empty
        else pd.DataFrame(columns=["label", "value"])
    )
    return [row for row in outflows if row["value"]], records(inflows[inflows["value"] != 0])


def _profit_loss_history(
    equity: pd.DataFrame, cashflow: pd.DataFrame, from_date: str, selected_date: str
) -> list[dict[str, Any]]:
    left = equity[["Date", "Estimated Equity"]]
    right = cashflow[["Date", "Cumulative Net Cash Flow"]]
    history = pd.merge(left, right, on="Date", how="outer").sort_values("Date")
    if history.empty:
        return []
    value_columns = ["Estimated Equity", "Cumulative Net Cash Flow"]
    history[value_columns] = history[value_columns].ffill().fillna(0.0)
    history["Total P/L"] = history[value_columns].sum(axis=1)
    baseline = history[history["Date"] < pd.Timestamp(from_date)].tail(1)
    columns = [*value_columns, "Total P/L"]
    old = baseline.iloc[0] if not baseline.empty else {column: 0 for column in columns}
    history = _period(history, from_date, selected_date)
    for column in columns:
        history[column] -= old[column]
    return records(history)


def build_real_estate_payload(*, selected_date: str, from_date: str) -> dict[str, Any]:
    data = load_real_estate_data(selected_date)
    period_data = data.period(from_date, selected_date)
    metrics = snapshot_metrics(data)
    metric_values = (
        ("Property Value", metrics["property_value"]),
        ("Outstanding Mortgage", metrics["outstanding_mortgage"]),
        ("Estimated Equity", metrics["estimated_equity"]),
        ("Net Cash Out", period_net_cash_out(period_data)),
    )
    equity = value_equity(data, selected_date)
    cashflow = monthly_cashflow(data)
    outflows, inflows = _real_estate_breakdowns(period_data)
    recent_outflows, recent_inflows = recent_cashflows(data, PAGE_SIZE)
    dated = [
        frame["Date"]
        for frame in (data.costs, data.inflows, data.values, data.mortgages)
        if not frame.empty
    ]
    return {
        "startDate": pd.concat(dated).min().strftime("%Y-%m-%d") if dated else selected_date,
        "metrics": [
            {"label": label, "value": value, "display": currency(value)}
            for label, value in metric_values
        ],
        "valueEquity": records(_period(equity, from_date, selected_date)),
        "cashflow": records(_period(monthly_cashflow(period_data), from_date, selected_date)),
        "profitLoss": _profit_loss_history(equity, cashflow, from_date, selected_date),
        "mortgageBalances": records(
            _period(mortgage_balances(data.mortgages), from_date, selected_date)
        ),
        "outflows": outflows,
        "inflows": inflows,
        "mortgages": table(mortgage_summary(data.mortgages)),
        "recentOutflows": table(recent_outflows),
        "recentInflows": table(recent_inflows),
    }
