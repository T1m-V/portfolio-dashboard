from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import pandas as pd

from blockchain_reader.datetime_utils import parse_daily_datetime, parse_transaction_datetime_series
from blockchain_reader.shared.prices import get_price_eur_on_or_before
from blockchain_reader.shared.token_metadata import load_token_metadata
from blockchain_reader.shared.valuation_routes import (
    ValuationRoute,
    build_symbol_protocol_map,
    classify_valuation_route,
)
from blockchain_reader.symbols import sanitize_symbol
from file_paths import (
    BLOCKCHAIN_BLOCK_MAP_FOLDER,
    BLOCKCHAIN_SNAPSHOT_FOLDER,
    BLOCKCHAIN_TRANSACTIONS_FOLDER,
    PRICES_FOLDER,
    PROTOCOL_UNDERLYING_TOKEN_FOLDER,
    TOKENS_FOLDER,
)

CHAIN = "arbitrum"
MATERIAL_QUANTITY_THRESHOLD = 1e-10
MATERIAL_PRINCIPAL_THRESHOLD = 1.0
TABLE_ROW_LIMIT = 100
TX_PAGE_SIZE = 10
TX_MAX_ROWS = 100


@dataclass
class ArbitrumHealthBundle:
    transactions: pd.DataFrame
    raw_snapshots: pd.DataFrame
    snapshots: pd.DataFrame
    base_ingredients: pd.DataFrame
    exceptions: pd.DataFrame
    block_map: pd.DataFrame
    errors: list[str]


DATASET_FILES: dict[str, Path] = {
    "transactions": BLOCKCHAIN_TRANSACTIONS_FOLDER / f"{CHAIN}_transactions.csv",
    "raw_snapshots": BLOCKCHAIN_SNAPSHOT_FOLDER / f"{CHAIN}_raw_snapshots.csv",
    "snapshots": BLOCKCHAIN_SNAPSHOT_FOLDER / f"{CHAIN}_snapshots.csv",
    "base_ingredients": PROTOCOL_UNDERLYING_TOKEN_FOLDER / f"{CHAIN}_base_ingredients.csv",
    "exceptions": PROTOCOL_UNDERLYING_TOKEN_FOLDER / f"{CHAIN}_base_ingredients_exceptions.csv",
    "block_map": BLOCKCHAIN_BLOCK_MAP_FOLDER / f"block_map_{CHAIN}.csv",
}

DATASET_COLUMNS: dict[str, list[str]] = {
    "transactions": [
        "TX Hash",
        "Date",
        "Qty in",
        "Token in",
        "Qty out",
        "Token out",
        "Type",
        "Fee",
        "Fee Token",
    ],
    "raw_snapshots": ["Date", "Coin", "Quantity", "Principal Invested"],
    "snapshots": ["Date", "Coin", "Quantity", "Principal Invested"],
    "base_ingredients": [
        "Date",
        "Coin",
        "Quantity",
        "ValuationRoute",
        "PriceSymbol",
        "PriceEUR",
        "EstimatedValueEUR",
        "HasDirectExposure",
        "HasProtocolExposure",
        "HasAaveExposure",
    ],
    "exceptions": ["Date", "Coin", "Quantity", "Reason", "EstimatedValueEUR", "Action"],
    "block_map": ["date", "block_number"],
}

DATASET_LABELS: dict[str, str] = {
    "transactions": "Transactions",
    "raw_snapshots": "Raw Snapshots",
    "snapshots": "Snapshots",
    "base_ingredients": "Base Ingredients",
    "exceptions": "Composition Exceptions",
    "block_map": "Block Map",
}

FRESHNESS_OK_MAX = 3
FRESHNESS_WARN_MAX = 14
PIPELINE_WARN_MAX = 1
MISSING_WARN_MAX = 2
EXCEPTIONS_WARN_MAX = 10


def _empty_frame(dataset_name: str) -> pd.DataFrame:
    return pd.DataFrame(columns=DATASET_COLUMNS[dataset_name])


def _parse_daily_series(series: pd.Series) -> pd.Series:
    parsed = pd.to_datetime(series.map(parse_daily_datetime), errors="coerce")
    return parsed.dt.normalize()


def _parse_transactions_frame(frame: pd.DataFrame) -> pd.DataFrame:
    parsed = frame.copy()
    if "Date" in parsed.columns:
        parsed["Date"] = parse_transaction_datetime_series(parsed["Date"])
    if "Fee" in parsed.columns:
        parsed["Fee"] = pd.to_numeric(parsed["Fee"], errors="coerce")
    return parsed


def _parse_snapshot_frame(frame: pd.DataFrame) -> pd.DataFrame:
    parsed = frame.copy()
    if "Date" in parsed.columns:
        parsed["Date"] = _parse_daily_series(parsed["Date"])
    if "Quantity" in parsed.columns:
        parsed["Quantity"] = pd.to_numeric(parsed["Quantity"], errors="coerce")
    if "Principal Invested" in parsed.columns:
        parsed["Principal Invested"] = pd.to_numeric(parsed["Principal Invested"], errors="coerce")
    return parsed


def _parse_base_ingredients_frame(frame: pd.DataFrame) -> pd.DataFrame:
    parsed = frame.copy()
    if "Date" in parsed.columns:
        parsed["Date"] = _parse_daily_series(parsed["Date"])
    if "Quantity" in parsed.columns:
        parsed["Quantity"] = pd.to_numeric(parsed["Quantity"], errors="coerce")
    if "PriceEUR" in parsed.columns:
        parsed["PriceEUR"] = pd.to_numeric(parsed["PriceEUR"], errors="coerce")
    if "EstimatedValueEUR" in parsed.columns:
        parsed["EstimatedValueEUR"] = pd.to_numeric(parsed["EstimatedValueEUR"], errors="coerce")
    for column in ("HasDirectExposure", "HasProtocolExposure", "HasAaveExposure"):
        if column not in parsed.columns:
            continue
        parsed[column] = (
            parsed[column]
            .map(
                lambda value: (
                    pd.NA if pd.isna(value) else str(value).strip().lower() in {"true", "1", "yes"}
                )
            )
            .astype("boolean")
        )
    return parsed


def _parse_exceptions_frame(frame: pd.DataFrame) -> pd.DataFrame:
    parsed = frame.copy()
    if "Date" in parsed.columns:
        parsed["Date"] = _parse_daily_series(parsed["Date"])
    if "Quantity" in parsed.columns:
        parsed["Quantity"] = pd.to_numeric(parsed["Quantity"], errors="coerce")
    if "EstimatedValueEUR" in parsed.columns:
        parsed["EstimatedValueEUR"] = pd.to_numeric(parsed["EstimatedValueEUR"], errors="coerce")
    return parsed


def _parse_block_map_frame(frame: pd.DataFrame) -> pd.DataFrame:
    parsed = frame.copy()
    if "date" in parsed.columns:
        parsed["date"] = _parse_daily_series(parsed["date"])
    return parsed


FRAME_PARSERS = {
    "transactions": _parse_transactions_frame,
    "raw_snapshots": _parse_snapshot_frame,
    "snapshots": _parse_snapshot_frame,
    "base_ingredients": _parse_base_ingredients_frame,
    "exceptions": _parse_exceptions_frame,
    "block_map": _parse_block_map_frame,
}


def _load_single_dataset(dataset_name: str, file_path: Path) -> tuple[pd.DataFrame, str | None]:
    if not file_path.exists():
        return _empty_frame(dataset_name=dataset_name), f"{dataset_name}: missing file {file_path}"

    try:
        frame = pd.read_csv(file_path)
    except Exception as exc:
        return _empty_frame(dataset_name=dataset_name), f"{dataset_name}: {exc}"

    parser = FRAME_PARSERS[dataset_name]
    parsed = parser(frame=frame)
    return parsed, None


def _to_date_or_none(value: object) -> pd.Timestamp | None:
    if value is None:
        return None
    parsed = pd.to_datetime(value, errors="coerce")
    if pd.isna(parsed):
        return None
    return pd.Timestamp(parsed).normalize()


def _max_date(frame: pd.DataFrame, date_column: str) -> pd.Timestamp | None:
    if frame.empty or date_column not in frame.columns:
        return None
    parsed = pd.to_datetime(frame[date_column], errors="coerce")
    parsed = parsed.dropna()
    if parsed.empty:
        return None
    return pd.Timestamp(parsed.max()).normalize()


def _lag_days(max_date: pd.Timestamp | None, today: pd.Timestamp) -> int | None:
    if max_date is None:
        return None
    return int((today.normalize() - max_date.normalize()).days)


def _classify_freshness_status(lag_days: int | None) -> str:
    if lag_days is None:
        return "CRIT"
    if lag_days <= FRESHNESS_OK_MAX:
        return "OK"
    if lag_days <= FRESHNESS_WARN_MAX:
        return "WARN"
    return "CRIT"


def _classify_pipeline_sync_status(spread_days: int | None) -> str:
    if spread_days is None:
        return "CRIT"
    if spread_days == 0:
        return "OK"
    if spread_days <= PIPELINE_WARN_MAX:
        return "WARN"
    return "CRIT"


def _classify_missing_price_status(missing_count: int) -> str:
    if missing_count == 0:
        return "OK"
    if missing_count <= MISSING_WARN_MAX:
        return "WARN"
    return "CRIT"


def _classify_exception_status(exception_count: int) -> str:
    if exception_count == 0:
        return "OK"
    if exception_count <= EXCEPTIONS_WARN_MAX:
        return "WARN"
    return "CRIT"


def _is_material_row(quantity: float, principal_invested: float) -> bool:
    return (
        abs(quantity) > MATERIAL_QUANTITY_THRESHOLD
        or abs(principal_invested) >= MATERIAL_PRINCIPAL_THRESHOLD
    )


def _normalize_symbol(value: object) -> str:
    return sanitize_symbol(value).upper()


def _normalize_selected_asset(selected_asset: str | None) -> str:
    if selected_asset is None:
        return "ALL"
    normalized = _normalize_symbol(selected_asset)
    if not normalized:
        return "ALL"
    return normalized


def _split_symbols(value: object) -> list[str]:
    if pd.isna(value):
        return []
    symbols: list[str] = []
    for part in str(value).split(","):
        cleaned = _normalize_symbol(part)
        if cleaned:
            symbols.append(cleaned)
    return symbols


def _tx_row_matches_asset(row: pd.Series, selected_asset: str) -> bool:
    if selected_asset == "ALL":
        return True

    token_candidates = []
    token_candidates.extend(_split_symbols(row.get("Token in")))
    token_candidates.extend(_split_symbols(row.get("Token out")))
    token_candidates.extend(_split_symbols(row.get("Fee Token")))
    return selected_asset in token_candidates


def load_arbitrum_health_bundle() -> ArbitrumHealthBundle:
    """
    Loads all Arbitrum health datasets used by the trial dashboard.

    returns:
        Parsed data bundle and load errors.
    """
    frames: dict[str, pd.DataFrame] = {}
    errors: list[str] = []

    for dataset_name, file_path in DATASET_FILES.items():
        frame, maybe_error = _load_single_dataset(dataset_name=dataset_name, file_path=file_path)
        frames[dataset_name] = frame
        if maybe_error:
            errors.append(maybe_error)

    return ArbitrumHealthBundle(
        transactions=frames["transactions"],
        raw_snapshots=frames["raw_snapshots"],
        snapshots=frames["snapshots"],
        base_ingredients=frames["base_ingredients"],
        exceptions=frames["exceptions"],
        block_map=frames["block_map"],
        errors=errors,
    )


def build_dataset_freshness_frame(
    bundle: ArbitrumHealthBundle, today: str | pd.Timestamp
) -> pd.DataFrame:
    """
    Builds dataset freshness lag metrics.

    args:
        bundle: Loaded Arbitrum data bundle.
        today: Reference date for lag calculations.

    returns:
        Dataset freshness frame with lag/status by dataset.
    """
    today_ts = pd.Timestamp(today).normalize()
    rows: list[dict[str, object]] = []
    dataset_specs = [
        ("transactions", bundle.transactions, "Date"),
        ("raw_snapshots", bundle.raw_snapshots, "Date"),
        ("snapshots", bundle.snapshots, "Date"),
        ("base_ingredients", bundle.base_ingredients, "Date"),
        ("exceptions", bundle.exceptions, "Date"),
        ("block_map", bundle.block_map, "date"),
    ]

    for dataset_name, frame, date_column in dataset_specs:
        latest_date = _max_date(frame=frame, date_column=date_column)
        lag_days = _lag_days(max_date=latest_date, today=today_ts)
        rows.append(
            {
                "Dataset": DATASET_LABELS[dataset_name],
                "Latest Date": latest_date,
                "Lag Days": lag_days,
                "Status": _classify_freshness_status(lag_days=lag_days),
            }
        )

    return pd.DataFrame(rows)


def filter_transactions_by_asset(
    transactions: pd.DataFrame,
    selected_asset: str | None = "ALL",
) -> pd.DataFrame:
    """
    Filters transaction rows by selected asset symbol.

    args:
        transactions: Transaction frame.
        selected_asset: Asset symbol or ALL.

    returns:
        Filtered transaction rows.
    """
    if transactions.empty:
        return transactions.copy()
    if "Date" not in transactions.columns:
        return transactions.copy()

    frame = transactions.copy()
    frame["Date"] = pd.to_datetime(frame["Date"], errors="coerce")
    frame = frame.dropna(subset=["Date"])

    asset = _normalize_selected_asset(selected_asset=selected_asset)
    if asset == "ALL":
        return frame.sort_values(by="Date")

    mask = frame.apply(_tx_row_matches_asset, axis=1, selected_asset=asset)
    return frame[mask].copy().sort_values(by="Date")


def build_tx_daily_frame(
    bundle: ArbitrumHealthBundle,
    selected_asset: str | None = "ALL",
) -> pd.DataFrame:
    """
    Builds daily transaction counts.

    args:
        bundle: Loaded Arbitrum data bundle.

    returns:
        Daily transaction count frame.
    """
    columns = ["Date", "Tx Count"]
    if bundle.transactions.empty or "Date" not in bundle.transactions.columns:
        return pd.DataFrame(columns=columns)

    filtered = filter_transactions_by_asset(
        transactions=bundle.transactions,
        selected_asset=selected_asset,
    )
    frame = filtered[["Date"]].copy()
    frame["Date"] = pd.to_datetime(frame["Date"], errors="coerce").dt.normalize()
    frame = frame.dropna(subset=["Date"])
    if frame.empty:
        return pd.DataFrame(columns=columns)

    grouped = frame.groupby("Date", as_index=False).size().rename(columns={"size": "Tx Count"})
    full_range = pd.date_range(start=grouped["Date"].min(), end=grouped["Date"].max(), freq="D")
    out = pd.DataFrame({"Date": full_range})
    out = pd.merge(left=out, right=grouped, on="Date", how="left")
    out["Tx Count"] = out["Tx Count"].fillna(0).astype(int)
    return out


def build_exception_daily_frame(
    bundle: ArbitrumHealthBundle,
    selected_asset: str | None = "ALL",
) -> pd.DataFrame:
    """
    Builds daily exception counts by reason.

    args:
        bundle: Loaded Arbitrum data bundle.

    returns:
        Daily exception counts split by reason.
    """
    columns = ["Date", "Reason", "Count"]
    if bundle.exceptions.empty:
        return pd.DataFrame(columns=columns)
    if "Date" not in bundle.exceptions.columns or "Reason" not in bundle.exceptions.columns:
        return pd.DataFrame(columns=columns)

    frame = bundle.exceptions.copy()
    if "Coin" not in frame.columns:
        frame["Coin"] = ""
    selected = _normalize_selected_asset(selected_asset=selected_asset)
    if selected != "ALL":
        frame["Coin"] = frame["Coin"].map(_normalize_symbol)
        frame = frame[frame["Coin"] == selected]

    frame = frame[["Date", "Reason"]].copy()
    frame["Date"] = pd.to_datetime(frame["Date"], errors="coerce").dt.normalize()
    frame["Reason"] = frame["Reason"].fillna("unknown").astype(str)
    frame = frame.dropna(subset=["Date"])
    if frame.empty:
        return pd.DataFrame(columns=columns)

    grouped = (
        frame.groupby(["Date", "Reason"], as_index=False)
        .size()
        .rename(columns={"size": "Count"})
        .sort_values(["Date", "Reason"])
    )
    return grouped


def filter_base_ingredients_by_asset(
    base_ingredients: pd.DataFrame,
    selected_asset: str | None = "ALL",
) -> pd.DataFrame:
    """
    Filters base-ingredients rows by selected asset symbol.

    args:
        base_ingredients: Base ingredients frame.
        selected_asset: Asset symbol or ALL.

    returns:
        Filtered base-ingredients rows.
    """
    if base_ingredients.empty:
        return base_ingredients.copy()
    if "Coin" not in base_ingredients.columns:
        return base_ingredients.copy()

    selected = _normalize_selected_asset(selected_asset=selected_asset)
    if selected == "ALL":
        return base_ingredients.copy()
    return base_ingredients[base_ingredients["Coin"].map(_normalize_symbol) == selected].copy()


def build_route_mix_daily_frame(
    bundle: ArbitrumHealthBundle,
    selected_asset: str | None = "ALL",
) -> pd.DataFrame:
    """
    Builds daily valuation-route mix from enriched base ingredients.

    args:
        bundle: Loaded Arbitrum data bundle.
        selected_asset: Asset symbol or ALL.

    returns:
        Daily route-value frame with Date, ValuationRoute, EstimatedValueEUR.
    """
    columns = ["Date", "ValuationRoute", "EstimatedValueEUR"]
    if bundle.base_ingredients.empty:
        return pd.DataFrame(columns=columns)
    required = {"Date", "ValuationRoute", "EstimatedValueEUR"}
    if not required.issubset(bundle.base_ingredients.columns):
        return pd.DataFrame(columns=columns)

    frame = filter_base_ingredients_by_asset(
        base_ingredients=bundle.base_ingredients,
        selected_asset=selected_asset,
    )
    frame["Date"] = pd.to_datetime(frame["Date"], errors="coerce").dt.normalize()
    frame["ValuationRoute"] = frame["ValuationRoute"].fillna("UNKNOWN").astype(str)
    frame["EstimatedValueEUR"] = pd.to_numeric(frame["EstimatedValueEUR"], errors="coerce")
    frame = frame.dropna(subset=["Date", "EstimatedValueEUR"])
    if frame.empty:
        return pd.DataFrame(columns=columns)

    grouped = (
        frame.assign(EstimatedValueEUR=frame["EstimatedValueEUR"].abs())
        .groupby(["Date", "ValuationRoute"], as_index=False)["EstimatedValueEUR"]
        .sum()
        .sort_values(["Date", "ValuationRoute"])
    )
    return grouped


def build_snapshot_valuation_frame(
    bundle: ArbitrumHealthBundle, chain: str = CHAIN
) -> pd.DataFrame:
    """
    Builds per-snapshot valuation rows using price history.

    args:
        bundle: Loaded Arbitrum data bundle.
        chain: Chain identifier used for LP pricing.

    returns:
        Snapshot valuation frame with market values and missing-price flags.
    """
    columns = [
        "Date",
        "Coin",
        "Quantity",
        "Principal Invested",
        "Price EUR",
        "Market Value EUR",
        "Valuation Route",
        "Is Material",
        "Missing Price",
    ]
    if bundle.snapshots.empty:
        return pd.DataFrame(columns=columns)
    required_columns = {"Date", "Coin", "Quantity", "Principal Invested"}
    if not required_columns.issubset(bundle.snapshots.columns):
        return pd.DataFrame(columns=columns)

    token_metadata = load_token_metadata(chain=chain, tokens_folder=TOKENS_FOLDER)
    symbol_protocol = build_symbol_protocol_map(token_metadata=token_metadata)

    rows: list[dict[str, object]] = []
    snapshots = bundle.snapshots.copy()
    snapshots["Date"] = pd.to_datetime(snapshots["Date"], errors="coerce").dt.normalize()
    snapshots["Quantity"] = pd.to_numeric(snapshots["Quantity"], errors="coerce").fillna(0.0)
    snapshots["Principal Invested"] = pd.to_numeric(
        snapshots["Principal Invested"], errors="coerce"
    ).fillna(0.0)
    snapshots = snapshots.dropna(subset=["Date"]).sort_values(["Date", "Coin"])

    for _, row in snapshots.iterrows():
        date_value = pd.Timestamp(row["Date"]).normalize()
        symbol = sanitize_symbol(row["Coin"])
        quantity = float(row["Quantity"])
        principal_invested = float(row["Principal Invested"])
        is_material = _is_material_row(quantity=quantity, principal_invested=principal_invested)

        if not symbol:
            rows.append(
                {
                    "Date": date_value,
                    "Coin": str(row["Coin"]),
                    "Quantity": quantity,
                    "Principal Invested": principal_invested,
                    "Price EUR": None,
                    "Market Value EUR": None,
                    "Valuation Route": ValuationRoute.DIRECT.value,
                    "Is Material": is_material,
                    "Missing Price": is_material,
                }
            )
            continue

        route = classify_valuation_route(symbol=symbol, symbol_protocol=symbol_protocol)
        use_lp_prices = route == ValuationRoute.PROTOCOL_DERIVED
        price = get_price_eur_on_or_before(
            symbol=symbol,
            as_of_date=date_value.date(),
            prices_folder=PRICES_FOLDER,
            chain=chain,
            use_lp_prices=use_lp_prices,
            fallback_to_oldest=False,
        )
        price_float = float(price) if price is not None else None
        market_value = quantity * price_float if price_float is not None else None
        missing_price = is_material and price_float is None

        rows.append(
            {
                "Date": date_value,
                "Coin": symbol,
                "Quantity": quantity,
                "Principal Invested": principal_invested,
                "Price EUR": price_float,
                "Market Value EUR": market_value,
                "Valuation Route": route.value,
                "Is Material": is_material,
                "Missing Price": missing_price,
            }
        )

    return pd.DataFrame(rows, columns=columns)


def build_holdings_valuation_frame(
    bundle: ArbitrumHealthBundle,
    chain: str = CHAIN,
) -> pd.DataFrame:
    """
    Builds rolled daily holdings valuation rows from base ingredients.

    args:
        bundle: Loaded Arbitrum data bundle.
        chain: Unused compatibility argument matching snapshot valuation.

    returns:
        Holdings valuation frame with current daily market values.
    """
    _ = chain
    columns = [
        "Date",
        "Coin",
        "Quantity",
        "Price EUR",
        "Market Value EUR",
        "Valuation Route",
        "Is Material",
        "Missing Price",
    ]
    if bundle.base_ingredients.empty:
        return pd.DataFrame(columns=columns)

    required_columns = {"Date", "Coin", "Quantity"}
    if not required_columns.issubset(bundle.base_ingredients.columns):
        return pd.DataFrame(columns=columns)

    holdings = bundle.base_ingredients.copy()
    holdings["Date"] = pd.to_datetime(holdings["Date"], errors="coerce").dt.normalize()
    holdings["Coin"] = holdings["Coin"].fillna("").astype(str)
    holdings["Quantity"] = pd.to_numeric(holdings["Quantity"], errors="coerce").fillna(0.0)
    holdings["Price EUR"] = pd.to_numeric(
        holdings.get("PriceEUR", pd.Series(index=holdings.index, dtype="float64")),
        errors="coerce",
    )
    holdings["Market Value EUR"] = pd.to_numeric(
        holdings.get("EstimatedValueEUR", pd.Series(index=holdings.index, dtype="float64")),
        errors="coerce",
    )
    missing_market_value = holdings["Market Value EUR"].isna() & holdings["Price EUR"].notna()
    holdings.loc[missing_market_value, "Market Value EUR"] = (
        holdings.loc[missing_market_value, "Quantity"]
        * holdings.loc[missing_market_value, "Price EUR"]
    )
    valuation_route = holdings.get("ValuationRoute")
    if valuation_route is None:
        holdings["Valuation Route"] = pd.Series("UNKNOWN", index=holdings.index)
    else:
        holdings["Valuation Route"] = valuation_route.fillna("UNKNOWN")
    holdings = holdings.dropna(subset=["Date"]).sort_values(["Date", "Coin"])
    if holdings.empty:
        return pd.DataFrame(columns=columns)

    market_values = pd.to_numeric(holdings["Market Value EUR"], errors="coerce")
    is_material = (holdings["Quantity"].abs() > MATERIAL_QUANTITY_THRESHOLD) | (
        market_values.abs() >= MATERIAL_PRINCIPAL_THRESHOLD
    )
    holdings["Is Material"] = is_material.fillna(False)
    holdings["Missing Price"] = holdings["Is Material"] & holdings["Price EUR"].isna()

    return holdings[columns].reset_index(drop=True)


def filter_valuation_by_asset(
    valuation: pd.DataFrame,
    selected_asset: str | None = "ALL",
) -> pd.DataFrame:
    """
    Filters valuation rows for one selected asset.

    args:
        valuation: Snapshot valuation frame.
        selected_asset: Asset symbol or ALL.

    returns:
        Filtered valuation frame.
    """
    if valuation.empty:
        return valuation.copy()

    selected = _normalize_selected_asset(selected_asset=selected_asset)
    if selected == "ALL":
        return valuation.copy()
    return valuation[valuation["Coin"].map(_normalize_symbol) == selected].copy()


def build_holdings_value_daily_frame(
    bundle: ArbitrumHealthBundle,
    selected_asset: str | None = "ALL",
    valuation: pd.DataFrame | None = None,
    snapshot_valuation: pd.DataFrame | None = None,
    chain: str = CHAIN,
) -> pd.DataFrame:
    """
    Builds daily rolled holdings value and forward-filled principal history.

    args:
        bundle: Loaded Arbitrum data bundle.
        selected_asset: Asset symbol or ALL.
        valuation: Optional prebuilt holdings valuation frame.
        snapshot_valuation: Optional prebuilt snapshot valuation frame.
        chain: Chain identifier for snapshot fallback.

    returns:
        Daily frame with Date, Market Value EUR, Principal Invested.
    """
    columns = ["Date", "Market Value EUR", "Principal Invested"]
    holdings_valuation = valuation
    if holdings_valuation is None:
        holdings_valuation = build_holdings_valuation_frame(bundle=bundle, chain=chain)
    holdings_valuation = filter_valuation_by_asset(
        valuation=holdings_valuation,
        selected_asset=selected_asset,
    )

    daily_market = pd.DataFrame(columns=["Date", "Market Value EUR"])
    if not holdings_valuation.empty and {
        "Date",
        "Market Value EUR",
    }.issubset(holdings_valuation.columns):
        daily_market = (
            holdings_valuation.assign(
                Date=pd.to_datetime(holdings_valuation["Date"], errors="coerce").dt.normalize(),
                **{
                    "Market Value EUR": pd.to_numeric(
                        holdings_valuation["Market Value EUR"], errors="coerce"
                    )
                },
            )
            .dropna(subset=["Date"])
            .groupby("Date", as_index=False)["Market Value EUR"]
            .sum()
            .sort_values("Date")
        )

    snapshot_rows = snapshot_valuation
    if snapshot_rows is None:
        snapshot_rows = build_snapshot_valuation_frame(bundle=bundle, chain=chain)
    snapshot_rows = filter_valuation_by_asset(
        valuation=snapshot_rows,
        selected_asset=selected_asset,
    )

    principal_daily = pd.DataFrame(columns=["Date", "Principal Invested"])
    if not snapshot_rows.empty and {"Date", "Principal Invested"}.issubset(snapshot_rows.columns):
        principal_daily = (
            snapshot_rows.assign(
                Date=pd.to_datetime(snapshot_rows["Date"], errors="coerce").dt.normalize(),
                **{
                    "Principal Invested": pd.to_numeric(
                        snapshot_rows["Principal Invested"], errors="coerce"
                    ).fillna(0.0)
                },
            )
            .dropna(subset=["Date"])
            .groupby("Date", as_index=False)["Principal Invested"]
            .sum()
            .sort_values("Date")
        )

    if daily_market.empty and principal_daily.empty:
        return pd.DataFrame(columns=columns)

    start_candidates = [
        frame["Date"].min()
        for frame in (daily_market, principal_daily)
        if not frame.empty and "Date" in frame.columns
    ]
    end_candidates = [
        frame["Date"].max()
        for frame in (daily_market, principal_daily)
        if not frame.empty and "Date" in frame.columns
    ]
    if not start_candidates or not end_candidates:
        return pd.DataFrame(columns=columns)

    full_range = pd.date_range(start=min(start_candidates), end=max(end_candidates), freq="D")
    out = pd.DataFrame({"Date": full_range})
    out = pd.merge(left=out, right=daily_market, on="Date", how="left")
    out = pd.merge(left=out, right=principal_daily, on="Date", how="left")
    out["Market Value EUR"] = pd.to_numeric(out["Market Value EUR"], errors="coerce").fillna(0.0)
    out["Principal Invested"] = (
        pd.to_numeric(out["Principal Invested"], errors="coerce").ffill().fillna(0.0)
    )
    return out[columns]


def list_invested_assets(
    valuation: pd.DataFrame,
    base_ingredients: pd.DataFrame | None = None,
    exceptions: pd.DataFrame | None = None,
) -> list[str]:
    """
    Lists selectable assets from material valuation rows.

    args:
        valuation: Snapshot valuation frame.

    returns:
        Sorted unique asset symbols.
    """
    if valuation.empty:
        return []

    assets: set[str] = set()
    frame = valuation.copy()
    frame["Is Material"] = frame["Is Material"].fillna(False)
    frame = frame[frame["Is Material"]]
    assets.update(
        {
            _normalize_symbol(symbol)
            for symbol in frame["Coin"].dropna().astype(str).tolist()
            if _normalize_symbol(symbol)
        }
    )

    if (
        base_ingredients is not None
        and not base_ingredients.empty
        and "Coin" in base_ingredients.columns
    ):
        base = base_ingredients.copy()
        if "Quantity" in base.columns:
            base["Quantity"] = pd.to_numeric(base["Quantity"], errors="coerce").fillna(0.0)
        else:
            base["Quantity"] = 0.0
        if "EstimatedValueEUR" in base.columns:
            base["EstimatedValueEUR"] = pd.to_numeric(base["EstimatedValueEUR"], errors="coerce")
        else:
            base["EstimatedValueEUR"] = pd.NA
        material = (base["Quantity"].abs() > MATERIAL_QUANTITY_THRESHOLD) | (
            pd.to_numeric(base["EstimatedValueEUR"], errors="coerce").abs()
            >= MATERIAL_PRINCIPAL_THRESHOLD
        )
        base = base[material]
        assets.update(
            {
                _normalize_symbol(symbol)
                for symbol in base["Coin"].dropna().astype(str).tolist()
                if _normalize_symbol(symbol)
            }
        )

    if exceptions is not None and not exceptions.empty and "Coin" in exceptions.columns:
        assets.update(
            {
                _normalize_symbol(symbol)
                for symbol in exceptions["Coin"].dropna().astype(str).tolist()
                if _normalize_symbol(symbol)
            }
        )

    assets.discard("ALL")
    assets.discard("")
    return sorted(assets)


def build_latest_transactions_frame(
    bundle: ArbitrumHealthBundle,
    selected_asset: str | None = "ALL",
    max_rows: int = TX_MAX_ROWS,
) -> pd.DataFrame:
    """
    Builds the latest filtered transactions frame.

    args:
        bundle: Loaded Arbitrum data bundle.
        selected_asset: Asset symbol or ALL.
        max_rows: Max number of latest rows.

    returns:
        Latest transactions sorted descending by date.
    """
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
    filtered = filter_transactions_by_asset(
        transactions=bundle.transactions,
        selected_asset=selected_asset,
    )
    if filtered.empty:
        return pd.DataFrame(columns=columns)

    available_columns = [column for column in columns if column in filtered.columns]
    latest = filtered.sort_values(by="Date", ascending=False).head(max_rows).copy()
    latest["Date"] = pd.to_datetime(latest["Date"], errors="coerce")
    latest["Date"] = latest["Date"].dt.strftime("%Y-%m-%d %H:%M:%S")
    return latest[available_columns].reset_index(drop=True)


def build_latest_health_metrics(
    bundle: ArbitrumHealthBundle,
    today: str | pd.Timestamp,
    selected_asset: str | None = "ALL",
    valuation: pd.DataFrame | None = None,
) -> dict[str, float | int | str]:
    """
    Builds top-level health KPIs.

    args:
        bundle: Loaded Arbitrum data bundle.
        today: Reference date for freshness KPIs.

    returns:
        KPI dictionary used by summary cards.
    """
    today_ts = pd.Timestamp(today).normalize()
    freshness = build_dataset_freshness_frame(bundle=bundle, today=today_ts)
    holdings_valuation = valuation
    if holdings_valuation is None:
        holdings_valuation = build_holdings_valuation_frame(bundle=bundle, chain=CHAIN)
    holdings_valuation = filter_valuation_by_asset(
        valuation=holdings_valuation,
        selected_asset=selected_asset,
    )
    snapshot_valuation: pd.DataFrame | None = None

    freshness_by_dataset = freshness.set_index("Dataset")
    tx_lag = freshness_by_dataset.at["Transactions", "Lag Days"]
    snapshot_lag = freshness_by_dataset.at["Snapshots", "Lag Days"]

    pipeline_max_dates = [
        _max_date(frame=bundle.transactions, date_column="Date"),
        _max_date(frame=bundle.raw_snapshots, date_column="Date"),
        _max_date(frame=bundle.snapshots, date_column="Date"),
    ]
    pipeline_present_dates = [d for d in pipeline_max_dates if d is not None]
    pipeline_sync_spread = None
    if len(pipeline_present_dates) == len(pipeline_max_dates):
        pipeline_sync_spread = int((max(pipeline_present_dates) - min(pipeline_present_dates)).days)

    latest_holdings_date = _max_date(frame=holdings_valuation, date_column="Date")
    latest_snapshot_date = _max_date(frame=bundle.snapshots, date_column="Date")
    latest_transaction_date = _max_date(frame=bundle.transactions, date_column="Date")
    latest_exception_date = _max_date(frame=bundle.exceptions, date_column="Date")

    missing_price_count = 0
    latest_estimated_value = 0.0
    base_frame = filter_base_ingredients_by_asset(
        base_ingredients=bundle.base_ingredients,
        selected_asset=selected_asset,
    )
    if (
        not base_frame.empty
        and "PriceEUR" in base_frame.columns
        and "Quantity" in base_frame.columns
    ):
        base_frame = base_frame.copy()
        base_frame["PriceEUR"] = pd.to_numeric(base_frame["PriceEUR"], errors="coerce")
        base_frame["Quantity"] = pd.to_numeric(base_frame["Quantity"], errors="coerce").fillna(0.0)
        if "EstimatedValueEUR" in base_frame.columns:
            base_frame["EstimatedValueEUR"] = pd.to_numeric(
                base_frame["EstimatedValueEUR"], errors="coerce"
            )
        else:
            base_frame["EstimatedValueEUR"] = pd.NA

        material_mask = (base_frame["Quantity"].abs() > MATERIAL_QUANTITY_THRESHOLD) | (
            pd.to_numeric(base_frame["EstimatedValueEUR"], errors="coerce").abs()
            >= MATERIAL_PRINCIPAL_THRESHOLD
        )
        missing_price_count = int((base_frame["PriceEUR"].isna() & material_mask).sum())
    else:
        snapshot_valuation = build_snapshot_valuation_frame(bundle=bundle, chain=CHAIN)
        snapshot_valuation = filter_valuation_by_asset(
            valuation=snapshot_valuation,
            selected_asset=selected_asset,
        )
        missing_price_count = int(
            (
                snapshot_valuation["Missing Price"].fillna(False)
                & snapshot_valuation["Is Material"].fillna(False)
            ).sum()
        )
    if latest_holdings_date is not None and not holdings_valuation.empty:
        holdings_rows = holdings_valuation[holdings_valuation["Date"] == latest_holdings_date]
        latest_estimated_value = float(
            pd.to_numeric(holdings_rows["Market Value EUR"], errors="coerce").dropna().sum()
        )
    elif latest_snapshot_date is not None:
        if snapshot_valuation is None:
            snapshot_valuation = build_snapshot_valuation_frame(bundle=bundle, chain=CHAIN)
            snapshot_valuation = filter_valuation_by_asset(
                valuation=snapshot_valuation,
                selected_asset=selected_asset,
            )
        snapshot_rows = snapshot_valuation[snapshot_valuation["Date"] == latest_snapshot_date]
        latest_estimated_value = float(
            pd.to_numeric(snapshot_rows["Market Value EUR"], errors="coerce").dropna().sum()
        )

    exception_count = 0
    if not bundle.exceptions.empty:
        exception_frame = bundle.exceptions.copy()
        if "Coin" not in exception_frame.columns:
            exception_frame["Coin"] = ""
        selected = _normalize_selected_asset(selected_asset=selected_asset)
        if selected != "ALL":
            exception_frame["Coin"] = exception_frame["Coin"].map(_normalize_symbol)
            exception_frame = exception_frame[exception_frame["Coin"] == selected]
        exception_count = len(exception_frame)

    tx_lag_value = int(tx_lag) if pd.notna(tx_lag) else -1
    snapshot_lag_value = int(snapshot_lag) if pd.notna(snapshot_lag) else -1

    return {
        "transactions_freshness_lag_days": tx_lag_value,
        "transactions_freshness_status": _classify_freshness_status(
            lag_days=None if tx_lag_value < 0 else tx_lag_value
        ),
        "snapshot_freshness_lag_days": snapshot_lag_value,
        "snapshot_freshness_status": _classify_freshness_status(
            lag_days=None if snapshot_lag_value < 0 else snapshot_lag_value
        ),
        "pipeline_sync_spread_days": -1 if pipeline_sync_spread is None else pipeline_sync_spread,
        "pipeline_sync_status": _classify_pipeline_sync_status(spread_days=pipeline_sync_spread),
        "missing_prices_overall_count": missing_price_count,
        "missing_prices_overall_status": _classify_missing_price_status(
            missing_count=missing_price_count
        ),
        "exceptions_overall_count": exception_count,
        "exceptions_overall_status": _classify_exception_status(exception_count=exception_count),
        "estimated_portfolio_value_eur": round(latest_estimated_value, 2),
        "latest_holdings_date": (
            latest_holdings_date.strftime("%Y-%m-%d") if latest_holdings_date is not None else ""
        ),
        "latest_snapshot_date": (
            latest_snapshot_date.strftime("%Y-%m-%d") if latest_snapshot_date is not None else ""
        ),
        "latest_transaction_date": (
            latest_transaction_date.strftime("%Y-%m-%d")
            if latest_transaction_date is not None
            else ""
        ),
        "latest_exception_date": (
            latest_exception_date.strftime("%Y-%m-%d") if latest_exception_date is not None else ""
        ),
        "today": today_ts.strftime("%Y-%m-%d"),
    }


def build_missing_price_frame(
    bundle: ArbitrumHealthBundle,
    selected_asset: str | None = "ALL",
    row_limit: int = TABLE_ROW_LIMIT,
) -> pd.DataFrame:
    """
    Builds the overall missing-price table frame.

    args:
        bundle: Loaded Arbitrum data bundle.
        selected_asset: Asset symbol or ALL.
        row_limit: Max rows to return.

    returns:
        Missing-price rows across all dates.
    """
    columns = [
        "Date",
        "Coin",
        "Quantity",
        "ValuationRoute",
        "PriceSymbol",
        "EstimatedValueEUR",
        "HasDirectExposure",
        "HasProtocolExposure",
        "HasAaveExposure",
    ]
    if bundle.base_ingredients.empty:
        return pd.DataFrame(columns=columns)

    frame = filter_base_ingredients_by_asset(
        base_ingredients=bundle.base_ingredients,
        selected_asset=selected_asset,
    ).copy()
    if frame.empty:
        return pd.DataFrame(columns=columns)

    required = {"Date", "Coin", "Quantity", "PriceEUR"}
    if not required.issubset(frame.columns):
        return pd.DataFrame(columns=columns)

    frame["PriceEUR"] = pd.to_numeric(frame["PriceEUR"], errors="coerce")
    frame["Quantity"] = pd.to_numeric(frame["Quantity"], errors="coerce").fillna(0.0)
    if "EstimatedValueEUR" in frame.columns:
        frame["EstimatedValueEUR"] = pd.to_numeric(frame["EstimatedValueEUR"], errors="coerce")
    else:
        frame["EstimatedValueEUR"] = pd.NA

    material_mask = (frame["Quantity"].abs() > MATERIAL_QUANTITY_THRESHOLD) | (
        pd.to_numeric(frame["EstimatedValueEUR"], errors="coerce").abs()
        >= MATERIAL_PRINCIPAL_THRESHOLD
    )
    frame = frame[frame["PriceEUR"].isna() & material_mask].copy()

    if frame.empty:
        return pd.DataFrame(columns=columns)

    for column in ("ValuationRoute", "PriceSymbol"):
        if column not in frame.columns:
            frame[column] = ""
    for column in ("HasDirectExposure", "HasProtocolExposure", "HasAaveExposure"):
        if column not in frame.columns:
            frame[column] = pd.NA

    frame["Date"] = pd.to_datetime(frame["Date"], errors="coerce").dt.strftime("%Y-%m-%d")
    frame["_abs_est"] = pd.to_numeric(frame["EstimatedValueEUR"], errors="coerce").abs().fillna(0.0)
    frame["_abs_qty"] = pd.to_numeric(frame["Quantity"], errors="coerce").abs().fillna(0.0)
    frame = frame.sort_values(
        by=["_abs_est", "_abs_qty", "Date", "Coin"],
        ascending=[False, False, False, True],
    ).head(row_limit)
    frame = frame[columns]
    return frame.reset_index(drop=True)


def build_exception_table_frame(
    bundle: ArbitrumHealthBundle,
    selected_asset: str | None = "ALL",
    row_limit: int = TABLE_ROW_LIMIT,
) -> pd.DataFrame:
    """
    Builds a compact overall exception table frame.

    args:
        bundle: Loaded Arbitrum data bundle.
        selected_asset: Asset symbol or ALL.
        row_limit: Max rows to return.

    returns:
        Exception rows capped to a fixed row limit.
    """
    columns = ["Date", "Coin", "Reason", "EstimatedValueEUR", "Action"]
    if bundle.exceptions.empty:
        return pd.DataFrame(columns=columns)

    frame = bundle.exceptions.copy()
    if "Coin" not in frame.columns:
        frame["Coin"] = ""
    selected = _normalize_selected_asset(selected_asset=selected_asset)
    if selected != "ALL":
        frame["Coin"] = frame["Coin"].map(_normalize_symbol)
        frame = frame[frame["Coin"] == selected]

    frame["Date"] = pd.to_datetime(frame["Date"], errors="coerce").dt.normalize()
    frame = frame.dropna(subset=["Date"])
    if frame.empty:
        return pd.DataFrame(columns=columns)

    frame = frame.sort_values(by=["Date", "Reason", "Coin"], ascending=[False, True, True])
    frame = frame.head(row_limit)
    frame["Date"] = frame["Date"].dt.strftime("%Y-%m-%d")
    return frame[columns].reset_index(drop=True)
