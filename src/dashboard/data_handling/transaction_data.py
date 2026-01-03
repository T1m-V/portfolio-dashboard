import json
from pathlib import Path

import pandas as pd

# Paths (keep these as you had them)
SNAPSHOT_PATH = Path(__file__).parents[3] / "data" / "transactions" / "portfolio_snapshot.csv"
PRICE_FOLDER_PATH = Path(__file__).parents[3] / "data" / "prices"
STOCK_METADATA_PATH = Path(__file__).parents[3] / "data" / "stock_metadata.json"

COLS_TO_FILL = [
    "Quantity",
    "Principal Invested",
    "Cumulative Fees",
    "Cumulative Taxes",
    "Gross Dividends",
]


def _load_stock_metadata() -> dict[str, dict[str, str]]:
    with open(STOCK_METADATA_PATH, "r") as f:
        return json.load(f)


def _process_price_history(
    df_prices: pd.DataFrame, isin: str, end_dt: pd.Timestamp
) -> pd.DataFrame:
    """Internal helper to clean and reindex price data for a single ISIN."""
    df_prices["Date"] = pd.to_datetime(df_prices["Date"])
    df_prices = df_prices[df_prices["Date"] <= end_dt]

    if df_prices.empty:
        return pd.DataFrame()

    df_prices = df_prices.set_index("Date")
    full_range = pd.date_range(start=df_prices.index.min(), end=end_dt, freq="D")
    currency = _load_stock_metadata().get(isin, {}).get("currency", "EUR")
    if currency != "EUR":
        fx_path = PRICE_FOLDER_PATH / f"{currency}_EUR.csv"
        if not fx_path.exists():
            error_msg = f"⚠️ Warning: No forex data for {currency}. Defaulting to 1.0"
            raise FileNotFoundError(error_msg)
        df_forex = pd.read_csv(fx_path)
        df_forex["Date"] = pd.to_datetime(df_forex["Date"])
        df_forex = df_forex.rename(columns={"Price": "FX_Rate"})

        # Merge FX into the prices dataframe
        df_prices = pd.merge(df_prices, df_forex[["Date", "FX_Rate"]], on="Date", how="left")

        # Multiply and clean up
        df_prices["Price"] = df_prices["Price"] * df_prices["FX_Rate"]
        df_prices = df_prices.drop(columns=["FX_Rate"]).set_index("Date")

    df_prices = df_prices.reindex(full_range).ffill().reset_index()
    df_prices = df_prices.rename(columns={"index": "Date"})
    df_prices["ISIN"] = isin

    return df_prices[["Date", "ISIN", "Price"]]


def _finalize_calculations(df: pd.DataFrame) -> pd.DataFrame:
    """Internal helper to apply name mapping and financial calculations."""
    stock_metadata = _load_stock_metadata()
    name_lookup = {isin: info["name"] for isin, info in stock_metadata.items()}
    df["Asset Name"] = df["ISIN"].map(name_lookup).fillna(df["ISIN"])
    df["Market Value"] = df["Quantity"] * df["Price"]
    return df


def load_and_process_data_group_stocks(
    end_date_str: str, isins: list[str] | None = None
) -> pd.DataFrame:
    end_dt = pd.to_datetime(end_date_str)

    # 1. Resolve File Paths
    if isins:
        file_paths = [PRICE_FOLDER_PATH / f"{isin}.csv" for isin in isins]
        # Check if files exist; raise error if any are missing
        for p in file_paths:
            if not p.exists():
                raise FileNotFoundError(f"Price file not found for ISIN: {p.stem}")
    else:
        file_paths = list(PRICE_FOLDER_PATH.glob("*.csv"))

    # 2. Bulk Price Loading
    price_frames = []
    for file_path in file_paths:
        df_raw = pd.read_csv(file_path)
        df_price = _process_price_history(df_prices=df_raw, isin=file_path.stem, end_dt=end_dt)
        if not df_price.empty:
            price_frames.append(df_price)

    if not price_frames:
        return pd.DataFrame()

    df_prices = pd.concat(price_frames, ignore_index=True)

    # 3. Bulk Portfolio Loading & Filtering
    df_port = pd.read_csv(SNAPSHOT_PATH)
    df_port["Date"] = pd.to_datetime(df_port["Date"])
    df_port = df_port[df_port["Date"] <= end_dt]

    # Optional: Filter portfolio by ISINs as well if list is provided
    if isins:
        df_port = df_port[df_port["ISIN"].isin(isins)]

    # 4. Merge & Fill (Grouped)
    df_merged = pd.merge(df_prices, df_port, on=["Date", "ISIN"], how="left")

    # Sort and Fill
    df_merged = df_merged.sort_values(["ISIN", "Date"])
    df_merged[COLS_TO_FILL] = df_merged.groupby("ISIN")[COLS_TO_FILL].ffill().fillna(0)

    return _finalize_calculations(df=df_merged)
