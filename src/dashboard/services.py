from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

import pandas as pd

from dashboard.data_handling.arbitrum_artifacts import (
    ArbitrumDashboardArtifacts,
    filter_selection,
    latest_rows_as_of,
    load_arbitrum_dashboard_artifacts,
    rows_through_date,
    selection_key,
)
from dashboard.data_handling.nexo_data import (
    get_nexo_start_date,
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
    get_stock_start_date,
    load_and_process_data_group_stocks,
    load_recent_stock_transactions,
)
from file_paths import CURRENCY_METADATA, STOCK_METADATA
from historical_transactions.portfolio_snapshots import get_forex_rate

PAGE_SIZE = 5
ARBITRUM_CHAIN = "arbitrum"


@dataclass(frozen=True)
class ModeOption:
    label: str
    value: str


STOCK_ANALYSIS_MODES = [
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
    ModeOption("Single Asset", "name"),
]
NEXO_COMPOSITION_MODES = [
    ModeOption("Asset Name", "name"),
    ModeOption("Asset Group", "group"),
    ModeOption("Currency", "currency"),
]
ARBITRUM_ANALYSIS_MODES = [
    ModeOption("Single Asset", "name"),
]
ARBITRUM_COMPOSITION_MODES = [
    ModeOption("Asset Name", "name"),
    ModeOption("Valuation Route", "route"),
    ModeOption("Exposure Type", "exposure"),
]
ARBITRUM_CURRENCY_OPTIONS = [
    ModeOption("EUR", "EUR"),
    ModeOption("USD", "USD"),
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


def _currency(value: float, currency: str = "EUR") -> str:
    decimals = 0 if abs(value) > 100 else 2
    return f"{currency} {value:,.{decimals}f}"


def _normalize_dashboard_currency(currency: str) -> str:
    normalized = str(currency or "EUR").upper()
    if normalized == "USD":
        return "USD"
    return "EUR"


def _convert_eur_value(
    value: Any,
    *,
    currency: str,
    date_value: Any,
) -> float | None:
    if pd.isna(value):
        return None

    value_float = float(value)
    if currency == "EUR":
        return value_float

    date_ts = pd.to_datetime(date_value, errors="coerce")
    if pd.isna(date_ts):
        return value_float

    eur_per_usd = float(get_forex_rate(currency="USD", date=date_ts.strftime("%Y-%m-%d")))
    return value_float / eur_per_usd


def _convert_eur_columns(
    frame: pd.DataFrame,
    *,
    currency: str,
    columns: list[str],
    fallback_date: str | pd.Timestamp,
) -> pd.DataFrame:
    if frame.empty or currency == "EUR":
        return frame.copy()

    converted = frame.copy()
    if "Date" in converted.columns:
        dates = converted["Date"]
    else:
        dates = pd.Series(fallback_date, index=converted.index)
    for column in columns:
        if column not in converted.columns:
            continue
        converted[column] = [
            _convert_eur_value(value, currency=currency, date_value=date_value)
            for value, date_value in zip(converted[column], dates, strict=True)
        ]
    return converted


def _date_window(*, selected_date: str, from_date: str) -> tuple[pd.Timestamp, pd.Timestamp]:
    end = pd.to_datetime(selected_date).normalize()
    start = pd.to_datetime(from_date).normalize()
    if start > end:
        start = end
    return start, end


def _date_window_strings(*, selected_date: str, from_date: str | None) -> tuple[str, str]:
    start, end = _date_window(
        selected_date=selected_date,
        from_date=from_date or selected_date,
    )
    return start.strftime("%Y-%m-%d"), end.strftime("%Y-%m-%d")


def _filter_period_rows(
    frame: pd.DataFrame,
    *,
    from_date: str,
    selected_date: str,
) -> pd.DataFrame:
    if frame.empty or "Date" not in frame.columns:
        return frame.copy()

    start, end = _date_window(selected_date=selected_date, from_date=from_date)
    dates = pd.to_datetime(frame["Date"])
    return frame[(dates >= start) & (dates <= end)].copy()


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


def _arbitrum_asset_options() -> list[dict[str, str]]:
    artifacts = load_arbitrum_dashboard_artifacts(chain=ARBITRUM_CHAIN)
    if artifacts.assets.empty:
        return []
    return [
        {"label": row["Label"], "value": row["Value"]}
        for _, row in artifacts.assets.sort_values("Label").iterrows()
        if str(row["Value"]).strip()
    ]


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
        "arbitrum": {
            "analysisModes": _mode_options(ARBITRUM_ANALYSIS_MODES),
            "compositionModes": _mode_options(ARBITRUM_COMPOSITION_MODES),
            "assets": _arbitrum_asset_options(),
            "currencies": _mode_options(ARBITRUM_CURRENCY_OPTIONS),
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
    from_date: str,
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

    _, end = _date_window(selected_date=selected_date, from_date=from_date)
    day = _investment_snapshot(frame=frame, target_date=end, include_target=True)
    if day.empty:
        return {
            "title": title,
            "empty": True,
            "metrics": [],
            "currentValue": 0,
            "profitLoss": 0,
        }

    start, _ = _date_window(selected_date=selected_date, from_date=from_date)
    baseline = _investment_snapshot(frame=frame, target_date=start, include_target=False)
    end_totals = _investment_totals(day)
    baseline_totals = _investment_totals(baseline)

    total_value = end_totals["market_value"]
    dividends = end_totals["dividends"] - baseline_totals["dividends"]
    fees = end_totals["fees"] - baseline_totals["fees"]
    taxes = end_totals["taxes"] - baseline_totals["taxes"]
    principal = end_totals["principal"] - baseline_totals["principal"]
    net_invested = principal + fees + taxes - dividends
    profit_loss = (total_value - baseline_totals["market_value"]) - net_invested
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


def _investment_snapshot(
    *,
    frame: pd.DataFrame,
    target_date: pd.Timestamp,
    include_target: bool,
) -> pd.DataFrame:
    if frame.empty or "Date" not in frame.columns:
        return pd.DataFrame()

    date_series = pd.to_datetime(frame["Date"])
    mask = date_series <= target_date if include_target else date_series < target_date
    candidates = frame[mask].copy()
    if candidates.empty:
        return pd.DataFrame()

    snapshot_date = pd.to_datetime(candidates["Date"]).max()
    return candidates[pd.to_datetime(candidates["Date"]) == snapshot_date].copy()


def _investment_totals(frame: pd.DataFrame) -> dict[str, float]:
    if frame.empty:
        return {
            "market_value": 0.0,
            "principal": 0.0,
            "fees": 0.0,
            "taxes": 0.0,
            "dividends": 0.0,
            "net_invested": 0.0,
        }

    fees = float(frame["Cumulative Fees"].sum())
    taxes = float(frame["Cumulative Taxes"].sum())
    dividends = float(frame["Gross Dividends"].sum())
    principal = float(frame["Principal Invested"].sum())
    return {
        "market_value": float(frame["Market Value"].sum()),
        "principal": principal,
        "fees": fees,
        "taxes": taxes,
        "dividends": dividends,
        "net_invested": principal + fees + taxes - dividends,
    }


def _investment_history(
    frame: pd.DataFrame,
    *,
    selected_date: str,
    from_date: str,
) -> list[dict[str, Any]]:
    if frame.empty or "Date" not in frame.columns:
        return []
    _, end = _date_window(selected_date=selected_date, from_date=from_date)
    history = frame[frame["Date"] <= end].copy()
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
    start, _ = _date_window(selected_date=selected_date, from_date=from_date)
    baseline_candidates = grouped[grouped["Date"] < start]
    if baseline_candidates.empty:
        baseline_market_value = 0.0
        baseline_invested = 0.0
    else:
        baseline = baseline_candidates.iloc[-1]
        baseline_market_value = float(baseline["Market Value"])
        baseline_invested = float(baseline["Invested Capital"])

    grouped = grouped[(grouped["Date"] >= start) & (grouped["Date"] <= end)].copy()
    if grouped.empty:
        return []

    grouped["Profit/Loss"] = (grouped["Market Value"] - baseline_market_value) - (
        grouped["Invested Capital"] - baseline_invested
    )
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
    from_date: str | None,
    mode: str,
    selection: str,
    composition: str,
) -> dict[str, Any]:
    from_date, selected_date = _date_window_strings(
        selected_date=selected_date,
        from_date=from_date,
    )
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
        "asOfDate": selected_date,
        "fromDate": from_date,
        "startDate": get_stock_start_date(isins=isins) or selected_date,
        "summary": _summarize_investment_frame(
            frame=frame,
            selected_date=selected_date,
            from_date=from_date,
            title=title,
        ),
        "composition": _stock_composition(
            frame=snapshot,
            mode=mode,
            selection=selection,
            composition=composition,
        ),
        "history": _investment_history(
            frame,
            selected_date=selected_date,
            from_date=from_date,
        ),
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
    from_date: str | None,
    mode: str,
    selection: str,
    composition: str,
) -> dict[str, Any]:
    from_date, selected_date = _date_window_strings(
        selected_date=selected_date,
        from_date=from_date,
    )
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
        "asOfDate": selected_date,
        "fromDate": from_date,
        "startDate": get_nexo_start_date(coins=coins) or selected_date,
        "summary": _summarize_investment_frame(
            frame=frame,
            selected_date=selected_date,
            from_date=from_date,
            title=title,
        ),
        "composition": _nexo_composition(
            frame=snapshot,
            mode=mode,
            selection=selection,
            composition=composition,
        ),
        "history": _investment_history(
            frame,
            selected_date=selected_date,
            from_date=from_date,
        ),
        "transactions": _table_payload(
            tx,
            columns=["Date", "Type", "Input", "Output", "USD Equivalent", "Details"],
        ),
    }


def _arbitrum_selected_asset(*, mode: str, selection: str) -> str:
    if mode == "name" and selection:
        return selection
    return "ALL"


def _arbitrum_title(*, mode: str, selection: str) -> str:
    if mode == "name" and selection:
        return f"Arbitrum: {selection}"
    return "Arbitrum Portfolio"


def _arbitrum_start_date(
    *, artifacts: ArbitrumDashboardArtifacts, selected_asset: str
) -> str | None:
    frame = filter_selection(artifacts.timeseries_daily, selected_asset)
    if frame.empty or "Date" not in frame.columns:
        return None

    dates = pd.to_datetime(frame["Date"], errors="coerce").dropna()
    if dates.empty:
        return None
    return dates.min().strftime("%Y-%m-%d")


def _limit_daily_frame(frame: pd.DataFrame, *, selected_date: str) -> pd.DataFrame:
    if frame.empty or "Date" not in frame.columns:
        return frame.copy()

    limited = frame.copy()
    limited["Date"] = pd.to_datetime(limited["Date"], errors="coerce").dt.normalize()
    limited = limited.dropna(subset=["Date"])
    return limited[limited["Date"] <= pd.Timestamp(selected_date).normalize()].copy()


def _latest_rows_as_of(frame: pd.DataFrame, *, selected_date: str) -> pd.DataFrame:
    if frame.empty or "Date" not in frame.columns:
        return frame.copy()

    dated = _limit_daily_frame(frame=frame, selected_date=selected_date)
    if dated.empty:
        return dated

    latest_date = dated["Date"].max()
    return dated[dated["Date"] == latest_date].copy()


def _artifact_value_history(
    *,
    artifacts: ArbitrumDashboardArtifacts,
    selected_asset: str,
    selected_date: str,
    currency: str,
) -> pd.DataFrame:
    frame = filter_selection(artifacts.timeseries_daily, selected_asset)
    frame = rows_through_date(frame=frame, selected_date=selected_date)
    if frame.empty:
        return pd.DataFrame(
            columns=["Date", "Market Value", "Invested Capital", "Profit/Loss", "Quantity"]
        )

    converted = _convert_eur_columns(
        frame,
        currency=currency,
        columns=["MarketValueEUR", "PrincipalInvestedEUR", "ProfitLossEUR"],
        fallback_date=selected_date,
    )
    converted = converted.rename(
        columns={
            "MarketValueEUR": "Market Value",
            "PrincipalInvestedEUR": "Invested Capital",
            "ProfitLossEUR": "Profit/Loss",
        }
    )
    return converted[["Date", "Market Value", "Invested Capital", "Profit/Loss", "Quantity"]]


def _artifact_summary(
    *,
    history: pd.DataFrame,
    artifacts: ArbitrumDashboardArtifacts,
    selected_asset: str,
    selected_date: str,
    title: str,
    currency: str,
) -> dict[str, Any]:
    latest = _latest_rows_as_of(frame=history, selected_date=selected_date)
    if latest.empty:
        current_value = 0.0
        net_invested = 0.0
        profit_loss = 0.0
    else:
        row = latest.iloc[-1]
        current_value = float(row.get("Market Value", 0.0) or 0.0)
        net_invested = float(row.get("Invested Capital", 0.0) or 0.0)
        profit_loss = float(row.get("Profit/Loss", 0.0) or 0.0)

    tx_rows = _artifact_transactions(
        artifacts=artifacts,
        selected_asset=selected_asset,
        selected_date=selected_date,
        max_rows=None,
    )

    return {
        "title": title,
        "empty": latest.empty,
        "currentValue": current_value,
        "profitLoss": profit_loss,
        "metrics": [
            {
                "label": "Current Value",
                "value": current_value,
                "display": _currency(current_value, currency),
            },
            {
                "label": "Net P/L",
                "value": profit_loss,
                "display": _currency(profit_loss, currency),
            },
            {
                "label": "Net Invested",
                "value": net_invested,
                "display": _currency(net_invested, currency),
            },
            {
                "label": "Transactions",
                "value": len(tx_rows),
                "display": f"{len(tx_rows):,}",
            },
        ],
    }


def _artifact_transactions(
    *,
    artifacts: ArbitrumDashboardArtifacts,
    selected_asset: str,
    selected_date: str,
    max_rows: int | None,
) -> pd.DataFrame:
    frame = artifacts.transactions_dashboard.copy()
    columns = [
        "Date",
        "Type",
        "Token in",
        "Qty in",
        "Token out",
        "Qty out",
        "Fee",
        "Fee Token",
        "TX Hash",
    ]
    if frame.empty:
        return pd.DataFrame(columns=columns)

    selected = selection_key(selected_asset)
    if selected != "ALL":
        frame = frame[
            frame["AssetKeys"]
            .fillna("")
            .astype(str)
            .str.split(";")
            .map(lambda keys: selected in keys)
        ].copy()
    frame["Date"] = pd.to_datetime(frame["Date"], errors="coerce")
    frame = frame.dropna(subset=["Date"])
    frame = frame[frame["Date"].dt.normalize() <= pd.Timestamp(selected_date).normalize()]
    frame = frame.sort_values("Date", ascending=False)
    if max_rows is not None:
        frame = frame.head(max_rows)
    frame["Date"] = frame["Date"].dt.strftime("%Y-%m-%d %H:%M:%S")
    return frame[[column for column in columns if column in frame.columns]].reset_index(drop=True)


def _artifact_composition(
    *,
    artifacts: ArbitrumDashboardArtifacts,
    selected_asset: str,
    selected_date: str,
    composition: str,
    currency: str,
) -> dict[str, Any]:
    frame = filter_selection(artifacts.composition_daily, selected_asset)
    frame = frame[frame["CompositionMode"].fillna("").astype(str) == composition].copy()
    frame = latest_rows_as_of(frame=frame, selected_date=selected_date)
    if frame.empty:
        return {"kind": "empty", "items": []}

    converted = _convert_eur_columns(
        frame,
        currency=currency,
        columns=["ValueEUR"],
        fallback_date=selected_date,
    )
    grouped = (
        converted.rename(columns={"Label": "label", "ValueEUR": "value"})
        .groupby("label", as_index=False)["value"]
        .sum()
        .sort_values("value", ascending=False)
        .head(12)
    )
    grouped["value"] = pd.to_numeric(grouped["value"], errors="coerce").fillna(0.0)
    grouped = grouped[grouped["value"].abs() > 0]
    if grouped.empty:
        return {"kind": "empty", "items": []}
    return {"kind": "breakdown", "items": _records(grouped)}


def _artifact_source_breakdown(
    *,
    artifacts: ArbitrumDashboardArtifacts,
    selected_asset: str,
    selected_date: str,
    currency: str,
) -> pd.DataFrame:
    if selection_key(selected_asset) == "ALL":
        return pd.DataFrame()

    frame = filter_selection(artifacts.source_daily, selected_asset)
    frame = latest_rows_as_of(frame=frame, selected_date=selected_date)
    if frame.empty:
        return pd.DataFrame()

    converted = _convert_eur_columns(
        frame,
        currency=currency,
        columns=["MarketValueEUR", "PrincipalInvestedEUR", "ProfitLossEUR"],
        fallback_date=selected_date,
    ).rename(
        columns={
            "MarketValueEUR": "Market Value",
            "PrincipalInvestedEUR": "Invested Capital",
            "ProfitLossEUR": "Profit/Loss",
            "ValuationRoute": "Valuation Route",
        }
    )
    converted["_abs_value"] = (
        pd.to_numeric(
            converted["Market Value"],
            errors="coerce",
        )
        .abs()
        .fillna(0.0)
    )
    converted = converted.sort_values("_abs_value", ascending=False).head(25)
    return converted


def build_arbitrum_payload(
    *,
    selected_date: str,
    from_date: str | None = None,
    mode: str = "full",
    selection: str = "",
    composition: str = "name",
    currency: str = "EUR",
) -> dict[str, Any]:
    if from_date:
        from_date, selected_date = _date_window_strings(
            selected_date=selected_date,
            from_date=from_date,
        )
    else:
        _, selected_date = _date_window_strings(
            selected_date=selected_date,
            from_date=selected_date,
        )

    artifacts = load_arbitrum_dashboard_artifacts(chain=ARBITRUM_CHAIN)
    selected_currency = _normalize_dashboard_currency(currency)
    selected_asset = _arbitrum_selected_asset(mode=mode, selection=selection)
    title = _arbitrum_title(mode=mode, selection=selection)
    start_date = _arbitrum_start_date(artifacts=artifacts, selected_asset=selected_asset)
    history = _artifact_value_history(
        artifacts=artifacts,
        selected_asset=selected_asset,
        selected_date=selected_date,
        currency=selected_currency,
    )
    tx_daily_source = rows_through_date(
        frame=filter_selection(artifacts.timeseries_daily, selected_asset),
        selected_date=selected_date,
    )
    if from_date:
        history = _filter_period_rows(
            history,
            from_date=from_date,
            selected_date=selected_date,
        )
        tx_daily_source = _filter_period_rows(
            tx_daily_source,
            from_date=from_date,
            selected_date=selected_date,
        )
    tx_daily = tx_daily_source[["Date", "TxCount"]].rename(columns={"TxCount": "Tx Count"})
    source_breakdown = _artifact_source_breakdown(
        artifacts=artifacts,
        selected_asset=selected_asset,
        selected_date=selected_date,
        currency=selected_currency,
    )
    latest_tx = _artifact_transactions(
        artifacts=artifacts,
        selected_asset=selected_asset,
        selected_date=selected_date,
        max_rows=25,
    )

    return {
        "title": title,
        "fromDate": from_date or start_date or selected_date,
        "startDate": start_date or selected_date,
        "currency": selected_currency,
        "mode": mode,
        "selection": selected_asset,
        "summary": _artifact_summary(
            history=history,
            artifacts=artifacts,
            selected_asset=selected_asset,
            selected_date=selected_date,
            title=title,
            currency=selected_currency,
        ),
        "transactionsDaily": _records(tx_daily),
        "valueHistory": _records(history),
        "composition": _artifact_composition(
            artifacts=artifacts,
            selected_asset=selected_asset,
            selected_date=selected_date,
            composition=composition,
            currency=selected_currency,
        ),
        "sourceBreakdown": _table_payload(
            source_breakdown,
            columns=[
                "Source",
                "Quantity",
                "Market Value",
                "Invested Capital",
                "Profit/Loss",
                "Valuation Route",
            ],
        ),
        "transactions": _table_payload(
            latest_tx,
            columns=[
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
        "warnings": artifacts.errors,
    }


def _resolve_limit(value: int | str | None) -> int | None:
    if value == "ALL":
        return None
    if value in [None, ""]:
        return 5
    return int(value)


def _real_estate_table(frame: pd.DataFrame) -> dict[str, Any]:
    return {"columns": list(frame.columns), "rows": _records(frame)}


def _real_estate_start_date(*frames: pd.DataFrame) -> str | None:
    date_parts = [
        pd.to_datetime(frame["Date"], errors="coerce").dropna()
        for frame in frames
        if not frame.empty and "Date" in frame.columns
    ]
    if not date_parts:
        return None
    return pd.concat(date_parts).min().strftime("%Y-%m-%d")


def _real_estate_period_net_cash_out(
    *,
    costs: pd.DataFrame,
    inflows: pd.DataFrame,
    mortgages: pd.DataFrame,
) -> float:
    total_costs = float(costs["Amount"].sum()) if not costs.empty else 0.0
    total_inflows = float(inflows["Amount"].sum()) if not inflows.empty else 0.0
    total_interest = float(mortgages["Interest Paid"].sum()) if not mortgages.empty else 0.0
    total_repaid = float(mortgages["Principal Repaid"].sum()) if not mortgages.empty else 0.0
    return round(total_costs + total_interest + total_repaid - total_inflows, 2)


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
    return _records(
        _real_estate_pl_frame(value_equity=value_equity, monthly_cashflow=monthly_cashflow)
    )


def _real_estate_pl_frame(
    value_equity: pd.DataFrame,
    monthly_cashflow: pd.DataFrame,
) -> pd.DataFrame:
    if value_equity.empty and monthly_cashflow.empty:
        return pd.DataFrame(
            columns=["Date", "Estimated Equity", "Cumulative Net Cash Flow", "Total P/L"]
        )

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
    return merged


def _real_estate_period_pl_breakdown(
    *,
    value_equity: pd.DataFrame,
    monthly_cashflow: pd.DataFrame,
    from_date: str,
    selected_date: str,
) -> list[dict]:
    frame = _real_estate_pl_frame(value_equity=value_equity, monthly_cashflow=monthly_cashflow)
    if frame.empty:
        return []

    start, end = _date_window(selected_date=selected_date, from_date=from_date)
    frame = frame[pd.to_datetime(frame["Date"]) <= end].sort_values(by="Date").copy()
    if frame.empty:
        return []

    value_columns = ["Estimated Equity", "Cumulative Net Cash Flow", "Total P/L"]
    baseline_candidates = frame[pd.to_datetime(frame["Date"]) < start]
    if baseline_candidates.empty:
        baseline = {column: 0.0 for column in value_columns}
    else:
        baseline_row = baseline_candidates.iloc[-1]
        baseline = {column: float(baseline_row[column]) for column in value_columns}

    period = frame[
        (pd.to_datetime(frame["Date"]) >= start) & (pd.to_datetime(frame["Date"]) <= end)
    ].copy()
    for column in value_columns:
        period[column] = pd.to_numeric(period[column], errors="coerce").fillna(0.0)
        period[column] = period[column] - baseline[column]

    if period.empty or not (pd.to_datetime(period["Date"]) == start).any():
        period = pd.concat(
            [
                pd.DataFrame(
                    [
                        {
                            "Date": start,
                            "Estimated Equity": 0.0,
                            "Cumulative Net Cash Flow": 0.0,
                            "Total P/L": 0.0,
                        }
                    ]
                ),
                period,
            ],
            ignore_index=True,
        )

    return _records(period.sort_values(by="Date").drop_duplicates(subset=["Date"], keep="last"))


def build_real_estate_payload(
    *,
    selected_date: str,
    from_date: str | None,
    asset: str,
    outflow_limit: int | str | None,
    inflow_limit: int | str | None,
) -> dict[str, Any]:
    from_date, selected_date = _date_window_strings(
        selected_date=selected_date,
        from_date=from_date,
    )
    bundle = load_real_estate_bundle(asof_date=selected_date)
    costs = filter_asset(frame=bundle.costs, asset=asset)
    inflows = filter_asset(frame=bundle.inflows, asset=asset)
    values = filter_asset(frame=bundle.values, asset=asset)
    mortgages = filter_asset(frame=bundle.mortgages, asset=asset)
    period_costs = _filter_period_rows(
        costs,
        from_date=from_date,
        selected_date=selected_date,
    )
    period_inflows = _filter_period_rows(
        inflows,
        from_date=from_date,
        selected_date=selected_date,
    )
    period_mortgages = _filter_period_rows(
        mortgages,
        from_date=from_date,
        selected_date=selected_date,
    )

    metrics = calculate_snapshot_metrics(
        costs=costs,
        inflows=inflows,
        values=values,
        mortgages=mortgages,
    )
    period_net_cash_out = _real_estate_period_net_cash_out(
        costs=period_costs,
        inflows=period_inflows,
        mortgages=period_mortgages,
    )
    lifetime_cashflow = build_monthly_cashflow_frame(
        costs=costs,
        inflows=inflows,
        mortgages=mortgages,
    )
    monthly_cashflow = build_monthly_cashflow_frame(
        costs=period_costs,
        inflows=period_inflows,
        mortgages=period_mortgages,
    )
    mortgage_balance = _filter_period_rows(
        build_mortgage_balance_frame(mortgages=mortgages),
        from_date=from_date,
        selected_date=selected_date,
    )
    value_equity_full = build_value_equity_frame(
        values=values,
        mortgages=mortgages,
        asof_date=selected_date,
    )
    value_equity = _filter_period_rows(
        value_equity_full,
        from_date=from_date,
        selected_date=selected_date,
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
        "asOfDate": selected_date,
        "fromDate": from_date,
        "startDate": _real_estate_start_date(costs, inflows, values, mortgages) or selected_date,
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
                    "value": period_net_cash_out,
                    "display": _currency(period_net_cash_out),
                },
            ],
        },
        "valueEquity": _records(value_equity),
        "cashflow": _records(monthly_cashflow),
        "plBreakdown": _real_estate_period_pl_breakdown(
            value_equity=value_equity_full,
            monthly_cashflow=lifetime_cashflow,
            from_date=from_date,
            selected_date=selected_date,
        ),
        "mortgageBalance": _records(mortgage_balance),
        "outflowBreakdown": _real_estate_outflow_breakdown(
            costs=period_costs,
            mortgages=period_mortgages,
        ),
        "inflowBreakdown": _real_estate_inflow_breakdown(inflows=period_inflows),
        "mortgageSummary": _real_estate_table(mortgage_summary),
        "recentOutflows": _real_estate_table(recent_outflows),
        "recentInflows": _real_estate_table(recent_inflows),
        "warnings": bundle.errors,
    }


def package_root() -> Path:
    return Path(__file__).parents[2]
