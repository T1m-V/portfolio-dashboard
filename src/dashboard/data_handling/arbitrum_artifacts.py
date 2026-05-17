from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import pandas as pd

from blockchain_reader.dashboard_artifacts import (
    ASSET_DAILY_COLUMNS,
    ASSETS_COLUMNS,
    COMPOSITION_DAILY_COLUMNS,
    SOURCE_DAILY_COLUMNS,
    TIMESERIES_DAILY_COLUMNS,
    TRANSACTIONS_DASHBOARD_COLUMNS,
)
from blockchain_reader.symbols import sanitize_symbol
from file_paths import BLOCKCHAIN_DASHBOARD_FOLDER

CHAIN = "arbitrum"


@dataclass
class ArbitrumDashboardArtifacts:
    asset_daily: pd.DataFrame
    timeseries_daily: pd.DataFrame
    composition_daily: pd.DataFrame
    source_daily: pd.DataFrame
    transactions_dashboard: pd.DataFrame
    assets: pd.DataFrame
    errors: list[str]


ARTIFACT_FILES: dict[str, tuple[str, list[str]]] = {
    "asset_daily": ("asset_daily.csv", ASSET_DAILY_COLUMNS),
    "timeseries_daily": ("timeseries_daily.csv", TIMESERIES_DAILY_COLUMNS),
    "composition_daily": ("composition_daily.csv", COMPOSITION_DAILY_COLUMNS),
    "source_daily": ("source_daily.csv", SOURCE_DAILY_COLUMNS),
    "transactions_dashboard": ("transactions_dashboard.csv", TRANSACTIONS_DASHBOARD_COLUMNS),
    "assets": ("assets.csv", ASSETS_COLUMNS),
}


def _artifact_root(chain: str = CHAIN) -> Path:
    return BLOCKCHAIN_DASHBOARD_FOLDER / chain


def _empty(columns: list[str]) -> pd.DataFrame:
    return pd.DataFrame(columns=columns)


def _load_artifact(path: Path, columns: list[str]) -> tuple[pd.DataFrame, str | None]:
    if not path.exists():
        return _empty(columns), f"missing artifact {path}; run build_arbitrum_dashboard_artifacts"

    try:
        frame = pd.read_csv(path)
    except Exception as exc:
        return _empty(columns), f"{path.name}: {exc}"

    for column in columns:
        if column not in frame.columns:
            frame[column] = pd.NA
    return frame[columns].copy(), None


def _parse_bool_column(series: pd.Series) -> pd.Series:
    return series.map(
        lambda value: False
        if pd.isna(value)
        else str(value).strip().lower() in {"true", "1", "yes"}
    )


def _parse_artifact_frame(name: str, frame: pd.DataFrame) -> pd.DataFrame:
    parsed = frame.copy()
    if "Date" in parsed.columns:
        parsed["Date"] = pd.to_datetime(parsed["Date"], errors="coerce")
        if name != "transactions_dashboard":
            parsed["Date"] = parsed["Date"].dt.normalize()

    numeric_columns = {
        "Quantity",
        "PriceEUR",
        "MarketValueEUR",
        "PrincipalInvestedEUR",
        "ProfitLossEUR",
        "TxCount",
        "ValueEUR",
    }
    for column in numeric_columns.intersection(parsed.columns):
        parsed[column] = pd.to_numeric(parsed[column], errors="coerce")

    for column in (
        "HasDirectExposure",
        "HasProtocolExposure",
        "HasAaveExposure",
        "MissingPrice",
        "IsMaterial",
    ):
        if column in parsed.columns:
            parsed[column] = _parse_bool_column(parsed[column])

    if name == "assets":
        parsed["Label"] = parsed["Label"].fillna("").astype(str)
        parsed["Value"] = parsed["Value"].fillna("").astype(str)

    return parsed


def load_arbitrum_dashboard_artifacts(chain: str = CHAIN) -> ArbitrumDashboardArtifacts:
    frames: dict[str, pd.DataFrame] = {}
    errors: list[str] = []
    root = _artifact_root(chain=chain)

    for name, (filename, columns) in ARTIFACT_FILES.items():
        frame, maybe_error = _load_artifact(path=root / filename, columns=columns)
        frames[name] = _parse_artifact_frame(name=name, frame=frame)
        if maybe_error:
            errors.append(maybe_error)

    return ArbitrumDashboardArtifacts(
        asset_daily=frames["asset_daily"],
        timeseries_daily=frames["timeseries_daily"],
        composition_daily=frames["composition_daily"],
        source_daily=frames["source_daily"],
        transactions_dashboard=frames["transactions_dashboard"],
        assets=frames["assets"],
        errors=errors,
    )


def selection_key(value: object) -> str:
    return sanitize_symbol(value).upper()


def filter_selection(frame: pd.DataFrame, selection: str) -> pd.DataFrame:
    if frame.empty or "Selection" not in frame.columns:
        return frame.copy()
    selected = selection_key(selection)
    return frame[frame["Selection"].map(selection_key) == selected].copy()


def latest_rows_as_of(frame: pd.DataFrame, selected_date: str) -> pd.DataFrame:
    if frame.empty or "Date" not in frame.columns:
        return frame.copy()

    selected = pd.Timestamp(selected_date).normalize()
    dated = frame.copy()
    dated["Date"] = pd.to_datetime(dated["Date"], errors="coerce").dt.normalize()
    dated = dated.dropna(subset=["Date"])
    dated = dated[dated["Date"] <= selected]
    if dated.empty:
        return dated

    latest_date = dated["Date"].max()
    return dated[dated["Date"] == latest_date].copy()


def rows_through_date(frame: pd.DataFrame, selected_date: str) -> pd.DataFrame:
    if frame.empty or "Date" not in frame.columns:
        return frame.copy()

    selected = pd.Timestamp(selected_date).normalize()
    dated = frame.copy()
    dated["Date"] = pd.to_datetime(dated["Date"], errors="coerce").dt.normalize()
    dated = dated.dropna(subset=["Date"])
    return dated[dated["Date"] <= selected].copy()
