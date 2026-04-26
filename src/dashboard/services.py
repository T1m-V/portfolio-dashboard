from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

import pandas as pd

from dashboard.data_handling.nexo_data import (
    list_nexo_coins,
    load_and_process_nexo_data,
    load_recent_nexo_transactions,
)
from dashboard.data_handling.real_estate_data import (
    build_monthly_cashflow_frame,
    build_mortgage_balance_frame,
    build_recent_inflows_frame,
    build_recent_outflows_frame,
    build_value_equity_frame,
    calculate_snapshot_metrics,
    filter_asset,
    list_real_estate_assets,
    load_real_estate_bundle,
    summarize_mortgages_from_rows,
)
from dashboard.data_handling.transaction_data import (
    load_and_process_data_group_stocks,
    load_recent_stock_transactions,
)
from file_paths import CURRENCY_METADATA, STOCK_METADATA

PAGE_SIZE = 5


@dataclass(frozen=True)
class ModeOption:
    label: str
    value: str


STOCK_ANALYSIS_MODES = [
    ModeOption("Full Portfolio", "full"),
    ModeOption("Asset Group", "group"),
    ModeOption("Region", "region"),
    ModeOption("Provider", "provider"),
    ModeOption("Single Asset", "name"),
]
STOCK_COMPOSITION_MODES = [
    ModeOption("Asset Name", "name"),
    ModeOption("Asset Group", "group"),
    ModeOption("Region", "region"),
    ModeOption("Provider", "provider"),
]
NEXO_ANALYSIS_MODES = [
    ModeOption("Full Portfolio", "full"),
    ModeOption("Asset Group", "group"),
    ModeOption("Currency", "currency"),
    ModeOption("Single Asset", "name"),
]
NEXO_COMPOSITION_MODES = [
    ModeOption("Asset Name", "name"),
    ModeOption("Asset Group", "group"),
    ModeOption("Currency", "currency"),
]


def _mode_options(options: list[ModeOption]) -> list[dict[str, str]]:
    return [{"label": option.label, "value": option.value} for option in options]


def _json_value(value: Any) -> Any:
    if pd.isna(value):
        return None
    if isinstance(value, pd.Timestamp):
        return value.strftime("%Y-%m-%d")
    return value


def _records(frame: pd.DataFrame) -> list[dict[str, Any]]:
    if frame.empty:
        return []
    output = frame.copy()
    for column in output.columns:
        if pd.api.types.is_datetime64_any_dtype(output[column]):
            output[column] = output[column].dt.strftime("%Y-%m-%d")
    return [
        {key: _json_value(value) for key, value in row.items()} for row in output.to_dict("records")
    ]


def _safe_frame(load_fn, *args, **kwargs) -> pd.DataFrame:
    try:
        return load_fn(*args, **kwargs)
    except (FileNotFoundError, ValueError, pd.errors.EmptyDataError):
        return pd.DataFrame()


def _currency(value: float) -> str:
    decimals = 0 if abs(value) > 100 else 2
    return f"EUR {value:,.{decimals}f}"


def _resolve_stock_isins(*, selection: str, mode: str) -> list[str]:
    if mode == "name":
        return [selection] if selection else []
    if mode == "full":
        return list(STOCK_METADATA.keys())
    return [isin for isin, info in STOCK_METADATA.items() if info.get(mode) == selection]


def _nexo_metadata_value(*, coin: str, mode: str) -> str:
    if mode == "name":
        return coin
    if mode == "group":
        return str(CURRENCY_METADATA.get(coin, {}).get("group", "Unknown"))
    if mode == "currency":
        return str(CURRENCY_METADATA.get(coin, {}).get("currency", "USD"))
    return ""


def _resolve_nexo_coins(*, selection: str, mode: str) -> list[str]:
    coins = list_nexo_coins()
    if mode == "full":
        return coins
    if mode == "name":
        return [selection] if selection else []
    return [coin for coin in coins if _nexo_metadata_value(coin=coin, mode=mode) == selection]


def build_options_payload() -> dict[str, Any]:
    stock_assets = [
        {
            "label": info.get("name", isin),
            "value": isin,
            "group": info.get("group", "Unknown"),
            "region": info.get("region", "Unknown"),
            "provider": info.get("provider", "Unknown"),
        }
        for isin, info in STOCK_METADATA.items()
    ]
    nexo_coins = [
        {
            "label": CURRENCY_METADATA.get(coin, {}).get("name", coin),
            "value": coin,
            "group": CURRENCY_METADATA.get(coin, {}).get("group", "Unknown"),
            "currency": CURRENCY_METADATA.get(coin, {}).get("currency", "USD"),
        }
        for coin in list_nexo_coins()
    ]
    return {
        "stocks": {
            "analysisModes": _mode_options(STOCK_ANALYSIS_MODES),
            "compositionModes": _mode_options(STOCK_COMPOSITION_MODES),
            "assets": stock_assets,
        },
        "nexo": {
            "analysisModes": _mode_options(NEXO_ANALYSIS_MODES),
            "compositionModes": _mode_options(NEXO_COMPOSITION_MODES),
            "assets": nexo_coins,
        },
        "realEstate": {
            "assets": [{"label": "All Assets", "value": "ALL"}]
            + [{"label": asset, "value": asset} for asset in list_real_estate_assets()]
        },
    }


def _stock_title(*, mode: str, selection: str) -> str:
    if mode == "full":
        return "Total Portfolio"
    if mode == "name":
        return STOCK_METADATA.get(selection, {}).get("name", selection)
    return f"{mode.title()}: {selection}"


def _nexo_title(*, mode: str, selection: str) -> str:
    if mode == "full":
        return "NEXO Portfolio"
    if mode == "name":
        return str(CURRENCY_METADATA.get(selection, {}).get("name", selection))
    return f"{mode.title()}: {selection}"


def _summarize_investment_frame(
    *,
    frame: pd.DataFrame,
    selected_date: str,
    title: str,
) -> dict[str, Any]:
    if frame.empty or "Date" not in frame.columns:
        return {
            "title": title,
            "empty": True,
            "metrics": [],
            "currentValue": 0,
            "profitLoss": 0,
        }

    day = frame[frame["Date"] == pd.to_datetime(selected_date)].copy()
    if day.empty:
        return {
            "title": title,
            "empty": True,
            "metrics": [],
            "currentValue": 0,
            "profitLoss": 0,
        }

    total_value = float(day["Market Value"].sum())
    dividends = float(day["Gross Dividends"].sum())
    fees = float(day["Cumulative Fees"].sum())
    taxes = float(day["Cumulative Taxes"].sum())
    net_invested = float(day["Principal Invested"].sum() + fees + taxes - dividends)
    profit_loss = total_value - net_invested
    return {
        "title": title,
        "empty": False,
        "currentValue": total_value,
        "profitLoss": profit_loss,
        "metrics": [
            {"label": "Current Value", "value": total_value, "display": _currency(total_value)},
            {"label": "Net P/L", "value": profit_loss, "display": _currency(profit_loss)},
            {"label": "Net Invested", "value": net_invested, "display": _currency(net_invested)},
            {"label": "Dividends", "value": dividends, "display": _currency(dividends)},
            {"label": "Fees", "value": fees, "display": _currency(fees)},
            {"label": "Taxes", "value": taxes, "display": _currency(taxes)},
        ],
    }


def _investment_history(frame: pd.DataFrame, selected_date: str) -> list[dict[str, Any]]:
    if frame.empty or "Date" not in frame.columns:
        return []
    history = frame[frame["Date"] <= pd.to_datetime(selected_date)].copy()
    history["Invested Capital"] = (
        history["Principal Invested"]
        + history["Cumulative Fees"]
        + history["Cumulative Taxes"]
        - history["Gross Dividends"]
    )
    grouped = (
        history.groupby("Date")
        .agg({"Market Value": "sum", "Invested Capital": "sum", "Quantity": "sum"})
        .reset_index()
    )
    grouped["Profit/Loss"] = grouped["Market Value"] - grouped["Invested Capital"]
    return _records(grouped)


def _stock_composition(
    *,
    frame: pd.DataFrame,
    mode: str,
    selection: str,
    composition: str,
) -> dict[str, Any]:
    if frame.empty:
        return {"kind": "empty", "items": []}
    if mode == "name":
        info = STOCK_METADATA.get(selection, {})
        return {
            "kind": "metadata",
            "items": [
                {"label": "Ticker", "value": info.get("ticker", "-")},
                {"label": "ISIN", "value": selection},
                {"label": "Region", "value": info.get("region", "-")},
                {"label": "Asset Group", "value": info.get("group", "-")},
                {"label": "Provider", "value": info.get("provider", "-")},
            ],
        }

    active = frame[frame["Quantity"] > 0.00001].copy()
    if active.empty:
        return {"kind": "empty", "items": []}
    if composition not in active.columns and "ISIN" in active.columns:
        active[composition] = active["ISIN"].map(
            lambda isin: STOCK_METADATA.get(isin, {}).get(composition, "Unknown")
        )
    grouped = active.groupby(composition, dropna=False)["Market Value"].sum().reset_index()
    grouped = grouped.rename(columns={composition: "label", "Market Value": "value"})
    return {"kind": "breakdown", "items": _records(grouped)}


def _nexo_composition(
    *,
    frame: pd.DataFrame,
    mode: str,
    selection: str,
    composition: str,
) -> dict[str, Any]:
    if frame.empty:
        return {"kind": "empty", "items": []}
    if mode == "name":
        info = CURRENCY_METADATA.get(selection, {})
        return {
            "kind": "metadata",
            "items": [
                {"label": "Ticker", "value": info.get("ticker", "-")},
                {"label": "Symbol", "value": selection},
                {"label": "Name", "value": info.get("name", selection)},
                {"label": "Group", "value": info.get("group", "Unknown")},
                {"label": "Currency", "value": info.get("currency", "USD")},
            ],
        }

    active = frame[frame["Quantity"].abs() > 0.00001].copy()
    if active.empty:
        return {"kind": "empty", "items": []}
    label_column = {
        "name": "Asset Name",
        "group": "Asset Group",
        "currency": "Currency",
    }[composition]
    grouped = active.groupby(label_column, dropna=False)["Market Value"].sum().reset_index()
    grouped = grouped.rename(columns={label_column: "label", "Market Value": "value"})
    return {"kind": "breakdown", "items": _records(grouped)}


def _table_payload(frame: pd.DataFrame, *, columns: list[str]) -> dict[str, Any]:
    visible = [column for column in columns if column in frame.columns]
    return {"columns": visible, "rows": _records(frame[visible] if visible else pd.DataFrame())}


def build_stock_payload(
    *,
    selected_date: str,
    mode: str,
    selection: str,
    composition: str,
) -> dict[str, Any]:
    isins = None if mode == "full" else _resolve_stock_isins(selection=selection, mode=mode)
    frame = _safe_frame(load_and_process_data_group_stocks, end_date_str=selected_date, isins=isins)
    title = _stock_title(mode=mode, selection=selection)
    snapshot = frame[frame["Date"] == pd.to_datetime(selected_date)] if not frame.empty else frame
    tx = _safe_frame(
        load_recent_stock_transactions,
        end_date_str=selected_date,
        isins=isins,
        limit=PAGE_SIZE,
    )
    return {
        "title": title,
        "summary": _summarize_investment_frame(
            frame=frame, selected_date=selected_date, title=title
        ),
        "composition": _stock_composition(
            frame=snapshot,
            mode=mode,
            selection=selection,
            composition=composition,
        ),
        "history": _investment_history(frame, selected_date),
        "transactions": _table_payload(
            tx,
            columns=[
                "Date",
                "Type",
                "Asset Name",
                "Quantity",
                "Price",
                "Currency",
                "Fees",
                "Taxes",
            ],
        ),
    }


def build_nexo_payload(
    *,
    selected_date: str,
    mode: str,
    selection: str,
    composition: str,
) -> dict[str, Any]:
    coins = None if mode == "full" else _resolve_nexo_coins(selection=selection, mode=mode)
    frame = _safe_frame(load_and_process_nexo_data, end_date_str=selected_date, coins=coins)
    title = _nexo_title(mode=mode, selection=selection)
    snapshot = frame[frame["Date"] == pd.to_datetime(selected_date)] if not frame.empty else frame
    tx = _safe_frame(
        load_recent_nexo_transactions,
        end_date_str=selected_date,
        coins=coins,
        limit=PAGE_SIZE,
    )
    if not tx.empty:
        tx = tx.copy()
        tx["Input"] = tx["Input Amount"].astype(str) + " " + tx["Input Currency"].astype(str)
        tx["Output"] = tx["Output Amount"].astype(str) + " " + tx["Output Currency"].astype(str)
    return {
        "title": title,
        "summary": _summarize_investment_frame(
            frame=frame, selected_date=selected_date, title=title
        ),
        "composition": _nexo_composition(
            frame=snapshot,
            mode=mode,
            selection=selection,
            composition=composition,
        ),
        "history": _investment_history(frame, selected_date),
        "transactions": _table_payload(
            tx,
            columns=["Date", "Type", "Input", "Output", "USD Equivalent", "Details"],
        ),
    }


def _resolve_limit(value: int | str | None) -> int | None:
    if value == "ALL":
        return None
    if value in [None, ""]:
        return 5
    return int(value)


def _real_estate_table(frame: pd.DataFrame) -> dict[str, Any]:
    return {"columns": list(frame.columns), "rows": _records(frame)}


def _real_estate_outflow_breakdown(costs: pd.DataFrame, mortgages: pd.DataFrame) -> list[dict]:
    breakdown_rows: list[dict[str, str | float]] = []

    if not costs.empty:
        grouped_costs = costs.groupby("Cost Type", as_index=False)["Amount"].sum()
        for _, row in grouped_costs.iterrows():
            breakdown_rows.append(
                {"label": f"Cost: {row['Cost Type']}", "value": float(row["Amount"])}
            )

    if not mortgages.empty:
        payment_rows = mortgages[mortgages["Entry Type"] == "PAYMENT"]
        breakdown_rows.append(
            {
                "label": "Mortgage Interest",
                "value": float(payment_rows["Interest Paid"].sum()),
            }
        )
        breakdown_rows.append(
            {
                "label": "Mortgage Repayment",
                "value": float(payment_rows["Principal Repaid"].sum()),
            }
        )

    frame = pd.DataFrame(breakdown_rows)
    if frame.empty:
        return []
    frame = frame[frame["value"] != 0].copy()
    return _records(frame)


def _real_estate_inflow_breakdown(inflows: pd.DataFrame) -> list[dict]:
    if inflows.empty:
        return []
    grouped = inflows.groupby("Inflow Type", as_index=False)["Amount"].sum()
    grouped = grouped.rename(columns={"Inflow Type": "label", "Amount": "value"})
    grouped = grouped[grouped["value"] != 0].copy()
    return _records(grouped)


def _real_estate_pl_breakdown(
    value_equity: pd.DataFrame,
    monthly_cashflow: pd.DataFrame,
) -> list[dict]:
    if value_equity.empty and monthly_cashflow.empty:
        return []

    equity_frame = (
        value_equity[["Date", "Estimated Equity"]]
        if not value_equity.empty
        else pd.DataFrame(columns=["Date", "Estimated Equity"])
    )
    cashflow_frame = (
        monthly_cashflow[["Date", "Cumulative Net Cash Flow"]]
        if not monthly_cashflow.empty
        else pd.DataFrame(columns=["Date", "Cumulative Net Cash Flow"])
    )
    merged = pd.merge(
        left=equity_frame,
        right=cashflow_frame,
        on="Date",
        how="outer",
    ).sort_values(by="Date")
    merged["Estimated Equity"] = pd.to_numeric(
        merged.get("Estimated Equity", 0),
        errors="coerce",
    )
    merged["Cumulative Net Cash Flow"] = pd.to_numeric(
        merged.get("Cumulative Net Cash Flow", 0),
        errors="coerce",
    )
    merged["Estimated Equity"] = merged["Estimated Equity"].ffill().fillna(0.0)
    merged["Cumulative Net Cash Flow"] = merged["Cumulative Net Cash Flow"].ffill().fillna(0.0)
    merged["Total P/L"] = merged["Estimated Equity"] + merged["Cumulative Net Cash Flow"]
    return _records(merged)


def build_real_estate_payload(
    *,
    selected_date: str,
    asset: str,
    outflow_limit: int | str | None,
    inflow_limit: int | str | None,
) -> dict[str, Any]:
    bundle = load_real_estate_bundle(asof_date=selected_date)
    costs = filter_asset(frame=bundle.costs, asset=asset)
    inflows = filter_asset(frame=bundle.inflows, asset=asset)
    values = filter_asset(frame=bundle.values, asset=asset)
    mortgages = filter_asset(frame=bundle.mortgages, asset=asset)

    metrics = calculate_snapshot_metrics(
        costs=costs,
        inflows=inflows,
        values=values,
        mortgages=mortgages,
    )
    monthly_cashflow = build_monthly_cashflow_frame(
        costs=costs,
        inflows=inflows,
        mortgages=mortgages,
    )
    mortgage_balance = build_mortgage_balance_frame(mortgages=mortgages)
    value_equity = build_value_equity_frame(
        values=values,
        mortgages=mortgages,
        asof_date=selected_date,
    )
    mortgage_summary = summarize_mortgages_from_rows(mortgages=mortgages)
    recent_outflows = build_recent_outflows_frame(
        costs=costs,
        mortgages=mortgages,
        n=_resolve_limit(outflow_limit),
    )
    recent_inflows = build_recent_inflows_frame(inflows=inflows, n=_resolve_limit(inflow_limit))

    return {
        "title": "Real Estate" if asset == "ALL" else asset,
        "summary": {
            "title": "Real Estate",
            "metrics": [
                {
                    "label": "Property Value",
                    "value": metrics["property_value"],
                    "display": _currency(metrics["property_value"]),
                },
                {
                    "label": "Outstanding Mortgage",
                    "value": metrics["outstanding_mortgage"],
                    "display": _currency(metrics["outstanding_mortgage"]),
                },
                {
                    "label": "Estimated Equity",
                    "value": metrics["estimated_equity"],
                    "display": _currency(metrics["estimated_equity"]),
                },
                {
                    "label": "Net Cash Out",
                    "value": metrics["net_cash_out"],
                    "display": _currency(metrics["net_cash_out"]),
                },
            ],
        },
        "valueEquity": _records(value_equity),
        "cashflow": _records(monthly_cashflow),
        "plBreakdown": _real_estate_pl_breakdown(
            value_equity=value_equity,
            monthly_cashflow=monthly_cashflow,
        ),
        "mortgageBalance": _records(mortgage_balance),
        "outflowBreakdown": _real_estate_outflow_breakdown(
            costs=costs,
            mortgages=mortgages,
        ),
        "inflowBreakdown": _real_estate_inflow_breakdown(inflows=inflows),
        "mortgageSummary": _real_estate_table(mortgage_summary),
        "recentOutflows": _real_estate_table(recent_outflows),
        "recentInflows": _real_estate_table(recent_inflows),
        "warnings": bundle.errors,
    }


def package_root() -> Path:
    return Path(__file__).parents[2]
