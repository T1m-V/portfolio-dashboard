from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import pandas as pd
from portfolio_core import active_context
from portfolio_crypto_data.dashboard_artifacts import (
    ASSETS_COLUMNS,
    COMPOSITION_DAILY_COLUMNS,
    SOURCE_DAILY_COLUMNS,
    TIMESERIES_DAILY_COLUMNS,
    TRANSACTIONS_DASHBOARD_COLUMNS,
)
from portfolio_crypto_data.symbols import sanitize_symbol

CHAIN = "arbitrum"

ARTIFACT_FILES = {
    "timeseries": ("timeseries_daily.csv", TIMESERIES_DAILY_COLUMNS),
    "composition": ("composition_daily.csv", COMPOSITION_DAILY_COLUMNS),
    "sources": ("source_daily.csv", SOURCE_DAILY_COLUMNS),
    "transactions": ("transactions_dashboard.csv", TRANSACTIONS_DASHBOARD_COLUMNS),
}


@dataclass(slots=True)
class ArbitrumArtifacts:
    timeseries: pd.DataFrame
    composition: pd.DataFrame
    sources: pd.DataFrame
    transactions: pd.DataFrame
    warnings: list[str]


def _read_artifact(path: Path, columns: list[str]) -> tuple[pd.DataFrame, str | None]:
    if not path.exists():
        return pd.DataFrame(columns=columns), f"Missing Arbitrum artifact: {path.name}"

    frame = pd.read_csv(path)
    if list(frame.columns) != columns:
        raise ValueError(
            f"Invalid Arbitrum artifact schema for {path.name}: "
            f"expected {columns}, got {list(frame.columns)}"
        )

    if "Date" in frame:
        frame["Date"] = pd.to_datetime(frame["Date"], format="mixed")
        if path.name != "transactions_dashboard.csv":
            frame["Date"] = frame["Date"].dt.normalize()

    numeric = {
        "Quantity",
        "MarketValueEUR",
        "PrincipalInvestedEUR",
        "ProfitLossEUR",
        "TxCount",
        "ValueEUR",
    }
    for column in numeric.intersection(frame.columns):
        frame[column] = pd.to_numeric(frame[column])
    return frame, None


def load_arbitrum_artifacts(chain: str = CHAIN) -> ArbitrumArtifacts:
    root = active_context().paths.dashboard_artifacts / chain
    frames: dict[str, pd.DataFrame] = {}
    warnings: list[str] = []
    for name, (filename, columns) in ARTIFACT_FILES.items():
        frames[name], warning = _read_artifact(root / filename, columns)
        if warning:
            warnings.append(warning)
    return ArbitrumArtifacts(**frames, warnings=warnings)


def load_arbitrum_assets(chain: str = CHAIN) -> pd.DataFrame:
    root = active_context().paths.dashboard_artifacts / chain
    frame, _ = _read_artifact(root / "assets.csv", ASSETS_COLUMNS)
    return frame


def selection_key(value: object) -> str:
    return sanitize_symbol(value).upper()


def select(frame: pd.DataFrame, selection: str) -> pd.DataFrame:
    key = selection_key(selection)
    return frame[frame["Selection"].map(selection_key) == key].copy()


def through_date(frame: pd.DataFrame, selected_date: str) -> pd.DataFrame:
    selected = pd.Timestamp(selected_date)
    return frame[frame["Date"] <= selected].copy()


def latest_as_of(frame: pd.DataFrame, selected_date: str) -> pd.DataFrame:
    frame = through_date(frame, selected_date)
    if frame.empty:
        return frame
    return frame[frame["Date"] == frame["Date"].max()].copy()
