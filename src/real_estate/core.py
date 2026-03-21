from __future__ import annotations

from pathlib import Path

import pandas as pd

from file_paths import (
    REAL_ESTATE_COSTS_FILE_NAME,
    REAL_ESTATE_FOLDER,
    REAL_ESTATE_INFLOWS_FILE_NAME,
    REAL_ESTATE_MORTGAGE_GLOB,
    REAL_ESTATE_OWNERSHIP_FILE_NAME,
    REAL_ESTATE_VALUES_FILE_NAME,
)

COST_COLUMNS = ["Asset", "Date", "Cost Type", "Amount", "Notes"]
INFLOW_COLUMNS = ["Asset", "Date", "Inflow Type", "Amount", "Notes"]
MORTGAGE_COLUMNS = [
    "Asset",
    "Mortgage ID",
    "Date",
    "Entry Type",
    "Initial Principal",
    "Interest Paid",
    "Principal Repaid",
    "Notes",
]
VALUE_COLUMNS = ["Asset", "Date", "Value", "Valuation Type", "Notes"]
OWNERSHIP_COLUMNS = ["Scope", "Identifier", "Ownership Share", "Notes"]


def _list_asset_folders() -> list[Path]:
    """
    Lists real-estate asset folders.

    returns:
        Sorted directories under the real-estate data root.
    """
    if not REAL_ESTATE_FOLDER.exists():
        return []

    return sorted([path for path in REAL_ESTATE_FOLDER.iterdir() if path.is_dir()])


def _parse_asof_date(asof_date: str | None) -> pd.Timestamp | None:
    """
    Parses an optional as-of date.

    args:
        asof_date: Optional date string (YYYY-MM-DD).

    returns:
        Parsed timestamp or None.
    """
    if asof_date is None:
        return pd.Timestamp.today().normalize()

    parsed = pd.to_datetime(asof_date, format="%Y-%m-%d", errors="coerce")
    if pd.isna(parsed):
        raise ValueError("Invalid asof_date. Use YYYY-MM-DD.")
    return parsed


def _apply_asof_filter(frame: pd.DataFrame, asof_timestamp: pd.Timestamp | None) -> pd.DataFrame:
    """
    Filters frame rows to Date <= as-of timestamp.

    args:
        frame: Input data frame with Date column.
        asof_timestamp: Optional cutoff timestamp.

    returns:
        Filtered frame.
    """
    if asof_timestamp is None or frame.empty:
        return frame

    return frame[frame["Date"] <= asof_timestamp].copy()


def _load_csv(file_path: Path, expected_columns: list[str]) -> pd.DataFrame:
    """
    Loads a CSV and validates the exact column contract.

    args:
        file_path: CSV file path.
        expected_columns: Required column order.

    returns:
        Loaded data frame with canonical columns.
    """
    if not file_path.exists():
        raise FileNotFoundError(f"CSV file not found: {file_path}")

    frame = pd.read_csv(file_path)
    columns = list(frame.columns)
    if columns != expected_columns:
        error_msg = (
            f"Invalid CSV schema for {file_path.name}. Expected {expected_columns}, got {columns}."
        )
        raise ValueError(error_msg)

    return frame[expected_columns].copy()


def _validate_date_column(frame: pd.DataFrame, column: str, file_name: str) -> pd.DataFrame:
    """
    Validates and parses a date column in YYYY-MM-DD format.

    args:
        frame: Input data frame.
        column: Date column name.
        file_name: Source file name used for error messages.

    returns:
        Frame with parsed datetime values in the date column.
    """
    parsed = pd.to_datetime(frame[column], format="%Y-%m-%d", errors="coerce")
    if parsed.isna().any():
        error_msg = f"Invalid date value detected in {file_name}:{column}. Use YYYY-MM-DD."
        raise ValueError(error_msg)

    frame[column] = parsed
    return frame


def _validate_positive_numeric_columns(
    frame: pd.DataFrame, columns: list[str], file_name: str, allow_zero: bool
) -> pd.DataFrame:
    """
    Validates numeric columns and enforces positive values.

    args:
        frame: Input data frame.
        columns: Numeric columns.
        file_name: Source file name used for error messages.
        allow_zero: Whether 0 is accepted.

    returns:
        Frame with numeric columns cast to float.
    """
    for column in columns:
        frame[column] = pd.to_numeric(frame[column], errors="coerce")
        if frame[column].isna().any():
            error_msg = f"Invalid numeric value detected in {file_name}:{column}."
            raise ValueError(error_msg)

        if allow_zero:
            invalid_mask = frame[column] < 0
        else:
            invalid_mask = frame[column] <= 0

        if invalid_mask.any():
            error_msg = f"Amounts in {file_name}:{column} must be positive."
            raise ValueError(error_msg)

    return frame


def _validate_numeric_columns(
    frame: pd.DataFrame, columns: list[str], file_name: str
) -> pd.DataFrame:
    """
    Validates numeric columns without sign constraints.

    args:
        frame: Input data frame.
        columns: Numeric columns.
        file_name: Source file name used for error messages.

    returns:
        Frame with numeric columns cast to float.
    """
    for column in columns:
        frame[column] = pd.to_numeric(frame[column], errors="coerce")
        if frame[column].isna().any():
            error_msg = f"Invalid numeric value detected in {file_name}:{column}."
            raise ValueError(error_msg)

    return frame


def _normalize_text_column(frame: pd.DataFrame, column: str) -> pd.DataFrame:
    """
    Coerces a column to string and strips surrounding whitespace.

    args:
        frame: Input data frame.
        column: Column name.

    returns:
        Frame with normalized text column.
    """
    frame[column] = frame[column].fillna("").astype(str).str.strip()
    return frame


def _ensure_asset_values(frame: pd.DataFrame, folder_name: str) -> pd.DataFrame:
    """
    Ensures asset values are populated.

    args:
        frame: Input data frame.
        folder_name: Asset-folder name fallback.

    returns:
        Frame with a non-empty Asset column.
    """
    frame = _normalize_text_column(frame=frame, column="Asset")
    if frame["Asset"].eq("").all():
        frame["Asset"] = folder_name
    return frame


def _load_ownership_config(asset_folder: Path) -> tuple[float, dict[str, float]]:
    """
    Loads optional ownership shares for an asset folder.

    args:
        asset_folder: Asset directory path.

    returns:
        Tuple of (asset_share, mortgage_share_by_id_lowercase).
    """
    file_path = asset_folder / REAL_ESTATE_OWNERSHIP_FILE_NAME
    if not file_path.exists():
        return 1.0, {}

    frame = _load_csv(file_path=file_path, expected_columns=OWNERSHIP_COLUMNS)
    if frame.empty:
        return 1.0, {}

    frame = _normalize_text_column(frame=frame, column="Scope")
    frame = _normalize_text_column(frame=frame, column="Identifier")
    frame = _normalize_text_column(frame=frame, column="Notes")
    frame["Scope"] = frame["Scope"].str.upper()
    frame["Ownership Share"] = pd.to_numeric(frame["Ownership Share"], errors="coerce")
    if frame["Ownership Share"].isna().any():
        raise ValueError(f"Invalid numeric value detected in {file_path.name}:Ownership Share.")
    if ((frame["Ownership Share"] <= 0) | (frame["Ownership Share"] > 1)).any():
        raise ValueError(f"Ownership Share in {file_path.name} must be in (0, 1].")

    valid_scopes = {"ASSET", "MORTGAGE"}
    if (~frame["Scope"].isin(valid_scopes)).any():
        raise ValueError(f"Invalid Scope value in {file_path.name}. Use ASSET or MORTGAGE.")

    asset_rows = frame[frame["Scope"] == "ASSET"]
    if len(asset_rows) > 1:
        raise ValueError(f"Only one ASSET row is allowed in {file_path.name}.")
    asset_share = float(asset_rows.iloc[0]["Ownership Share"]) if len(asset_rows) == 1 else 1.0

    mortgage_rows = frame[frame["Scope"] == "MORTGAGE"]
    if mortgage_rows["Identifier"].eq("").any():
        raise ValueError(f"MORTGAGE rows require a non-empty Identifier in {file_path.name}.")
    if mortgage_rows["Identifier"].str.lower().duplicated().any():
        raise ValueError(f"Duplicate mortgage Identifier values detected in {file_path.name}.")

    mortgage_shares = {
        row["Identifier"].strip().lower(): float(row["Ownership Share"])
        for _, row in mortgage_rows.iterrows()
    }
    return asset_share, mortgage_shares


def load_home_costs(asof_date: str | None = None) -> pd.DataFrame:
    """
    Loads and validates home costs.

    args:
        asof_date: Optional filter date (YYYY-MM-DD). Defaults to today.

    returns:
        Canonical home-cost frame.
    """
    asof_timestamp = _parse_asof_date(asof_date=asof_date)
    frames: list[pd.DataFrame] = []

    for asset_folder in _list_asset_folders():
        asset_share, _ = _load_ownership_config(asset_folder=asset_folder)
        file_path = asset_folder / REAL_ESTATE_COSTS_FILE_NAME
        if not file_path.exists():
            continue

        frame = _load_csv(file_path=file_path, expected_columns=COST_COLUMNS)
        frame = _validate_date_column(frame=frame, column="Date", file_name=file_path.name)
        frame = _validate_positive_numeric_columns(
            frame=frame, columns=["Amount"], file_name=file_path.name, allow_zero=False
        )
        frame = _ensure_asset_values(frame=frame, folder_name=asset_folder.name)
        frame = _normalize_text_column(frame=frame, column="Cost Type")
        frame = _normalize_text_column(frame=frame, column="Notes")
        frame["Amount"] = frame["Amount"] * asset_share
        frame = _apply_asof_filter(frame=frame, asof_timestamp=asof_timestamp)
        if frame.empty:
            continue
        frames.append(frame[COST_COLUMNS])

    if not frames:
        return pd.DataFrame(columns=COST_COLUMNS)

    return pd.concat(frames, ignore_index=True)[COST_COLUMNS]


def load_home_inflows(asof_date: str | None = None) -> pd.DataFrame:
    """
    Loads and validates home inflows.

    args:
        asof_date: Optional filter date (YYYY-MM-DD). Defaults to today.

    returns:
        Canonical inflow frame.
    """
    asof_timestamp = _parse_asof_date(asof_date=asof_date)
    frames: list[pd.DataFrame] = []

    for asset_folder in _list_asset_folders():
        asset_share, _ = _load_ownership_config(asset_folder=asset_folder)
        file_path = asset_folder / REAL_ESTATE_INFLOWS_FILE_NAME
        if not file_path.exists():
            continue

        frame = _load_csv(file_path=file_path, expected_columns=INFLOW_COLUMNS)
        frame = _validate_date_column(frame=frame, column="Date", file_name=file_path.name)
        frame = _validate_positive_numeric_columns(
            frame=frame,
            columns=["Amount"],
            file_name=file_path.name,
            allow_zero=False,
        )
        frame = _ensure_asset_values(frame=frame, folder_name=asset_folder.name)
        frame = _normalize_text_column(frame=frame, column="Inflow Type")
        frame = _normalize_text_column(frame=frame, column="Notes")
        frame["Amount"] = frame["Amount"] * asset_share
        frame = _apply_asof_filter(frame=frame, asof_timestamp=asof_timestamp)
        if frame.empty:
            continue
        frames.append(frame[INFLOW_COLUMNS])

    if not frames:
        return pd.DataFrame(columns=INFLOW_COLUMNS)

    return pd.concat(frames, ignore_index=True)[INFLOW_COLUMNS]


def load_home_values(asof_date: str | None = None) -> pd.DataFrame:
    """
    Loads and validates real-estate valuation history.

    args:
        asof_date: Optional filter date (YYYY-MM-DD). Defaults to today.

    returns:
        Canonical valuation frame.
    """
    asof_timestamp = _parse_asof_date(asof_date=asof_date)
    frames: list[pd.DataFrame] = []

    for asset_folder in _list_asset_folders():
        asset_share, _ = _load_ownership_config(asset_folder=asset_folder)
        file_path = asset_folder / REAL_ESTATE_VALUES_FILE_NAME
        if not file_path.exists():
            continue

        frame = _load_csv(file_path=file_path, expected_columns=VALUE_COLUMNS)
        frame = _validate_date_column(frame=frame, column="Date", file_name=file_path.name)
        frame = _validate_positive_numeric_columns(
            frame=frame, columns=["Value"], file_name=file_path.name, allow_zero=False
        )
        frame = _ensure_asset_values(frame=frame, folder_name=asset_folder.name)
        frame = _normalize_text_column(frame=frame, column="Valuation Type")
        frame = _normalize_text_column(frame=frame, column="Notes")
        frame["Value"] = frame["Value"] * asset_share
        frame = _apply_asof_filter(frame=frame, asof_timestamp=asof_timestamp)
        if frame.empty:
            continue
        frames.append(frame[VALUE_COLUMNS])

    if not frames:
        return pd.DataFrame(columns=VALUE_COLUMNS)

    return pd.concat(frames, ignore_index=True)[VALUE_COLUMNS]


def _validate_mortgage_frame(frame: pd.DataFrame, file_name: str) -> pd.DataFrame:
    """
    Validates mortgage rows and ORIGINATION/PAYMENT ordering.

    args:
        frame: Mortgage data frame.
        file_name: Source file name used for error messages.

    returns:
        Canonical mortgage frame.
    """
    if frame.empty:
        raise ValueError(f"Mortgage file {file_name} cannot be empty.")

    frame = _validate_date_column(frame=frame, column="Date", file_name=file_name)
    frame = _validate_numeric_columns(
        frame=frame,
        columns=["Initial Principal", "Interest Paid", "Principal Repaid"],
        file_name=file_name,
    )
    frame = _normalize_text_column(frame=frame, column="Asset")
    frame = _normalize_text_column(frame=frame, column="Mortgage ID")
    frame = _normalize_text_column(frame=frame, column="Entry Type")
    frame = _normalize_text_column(frame=frame, column="Notes")

    first_row = frame.iloc[0]
    if first_row["Entry Type"] != "ORIGINATION":
        error_msg = f"Mortgage file {file_name} must start with Entry Type ORIGINATION."
        raise ValueError(error_msg)
    if first_row["Initial Principal"] == 0:
        error_msg = f"First row Initial Principal must be non-zero in {file_name}."
        raise ValueError(error_msg)

    if len(frame) > 1:
        payment_rows = frame.iloc[1:]
        if (payment_rows["Entry Type"] != "PAYMENT").any():
            error_msg = f"Rows after ORIGINATION must use Entry Type PAYMENT in {file_name}."
            raise ValueError(error_msg)
        if (payment_rows["Initial Principal"] != 0).any():
            error_msg = f"PAYMENT rows must have Initial Principal = 0 in {file_name}."
            raise ValueError(error_msg)
        mortgage_sign = 1 if first_row["Initial Principal"] > 0 else -1
        if ((payment_rows["Interest Paid"] * mortgage_sign) < 0).any():
            error_msg = f"Interest Paid sign must match mortgage direction in {file_name}."
            raise ValueError(error_msg)
        if ((payment_rows["Principal Repaid"] * mortgage_sign) < 0).any():
            error_msg = f"Principal Repaid sign must match mortgage direction in {file_name}."
            raise ValueError(error_msg)

    return frame[MORTGAGE_COLUMNS]


def load_mortgage_files(asof_date: str | None = None) -> pd.DataFrame:
    """
    Loads and validates all mortgage CSV files.

    args:
        asof_date: Optional filter date (YYYY-MM-DD). Defaults to today.

    returns:
        Canonical mortgage frame across all mortgage files.
    """
    asof_timestamp = _parse_asof_date(asof_date=asof_date)
    frames: list[pd.DataFrame] = []
    for asset_folder in _list_asset_folders():
        asset_share, mortgage_shares = _load_ownership_config(asset_folder=asset_folder)
        mortgage_files = sorted(asset_folder.glob(REAL_ESTATE_MORTGAGE_GLOB))
        for file_path in mortgage_files:
            frame = _load_csv(file_path=file_path, expected_columns=MORTGAGE_COLUMNS)
            frame = _validate_mortgage_frame(frame=frame, file_name=file_path.name)
            frame = _ensure_asset_values(frame=frame, folder_name=asset_folder.name)
            shares = (
                frame["Mortgage ID"]
                .astype(str)
                .str.strip()
                .str.lower()
                .map(mortgage_shares)
                .fillna(asset_share)
            )
            for column in ["Initial Principal", "Interest Paid", "Principal Repaid"]:
                frame[column] = frame[column] * shares
            frame = _apply_asof_filter(frame=frame, asof_timestamp=asof_timestamp)
            if frame.empty:
                continue
            frames.append(frame)

    if not frames:
        return pd.DataFrame(columns=MORTGAGE_COLUMNS)

    return pd.concat(frames, ignore_index=True)[MORTGAGE_COLUMNS]


def summarize_mortgages(asof_date: str | None = None) -> pd.DataFrame:
    """
    Summarizes mortgage totals per asset and mortgage id.

    args:
        asof_date: Optional filter date (YYYY-MM-DD). Defaults to today.

    returns:
        Summary frame with outstanding principal and cash out.
    """
    frame = load_mortgage_files(asof_date=asof_date)
    output_columns = [
        "Asset",
        "Mortgage ID",
        "Initial Principal",
        "Interest Paid",
        "Principal Repaid",
        "Outstanding Principal",
        "Cash Out",
    ]
    if frame.empty:
        return pd.DataFrame(columns=output_columns)

    origination_mask = frame["Entry Type"] == "ORIGINATION"
    grouped = (
        frame.groupby(["Asset", "Mortgage ID"], as_index=False)
        .agg(
            {
                "Initial Principal": "sum",
                "Interest Paid": "sum",
                "Principal Repaid": "sum",
            }
        )
        .rename(columns={"Initial Principal": "Initial Principal"})
    )

    # Guard against malformed duplicate ORIGINATION rows in a single file.
    originations_per_group = (
        frame[origination_mask]
        .groupby(["Asset", "Mortgage ID"], as_index=False)
        .size()
        .rename(columns={"size": "origination_count"})
    )
    if (originations_per_group["origination_count"] != 1).any():
        raise ValueError("Each mortgage must have exactly one ORIGINATION row.")

    grouped["Outstanding Principal"] = grouped["Initial Principal"] - grouped["Principal Repaid"]
    grouped["Cash Out"] = grouped["Interest Paid"] + grouped["Principal Repaid"]
    numeric_cols = [
        "Initial Principal",
        "Interest Paid",
        "Principal Repaid",
        "Outstanding Principal",
        "Cash Out",
    ]
    grouped[numeric_cols] = grouped[numeric_cols].round(2)
    return grouped[output_columns].sort_values(by=["Asset", "Mortgage ID"]).reset_index(drop=True)


def summarize_real_estate(asof_date: str | None = None) -> pd.DataFrame:
    """
    Summarizes real estate cashflows per asset.

    args:
        asof_date: Optional filter date (YYYY-MM-DD). Defaults to today.

    returns:
        Asset-level summary with costs, inflows, mortgage and property values.
    """
    costs = load_home_costs(asof_date=asof_date)
    inflows = load_home_inflows(asof_date=asof_date)
    mortgages = summarize_mortgages(asof_date=asof_date)
    values = load_home_values(asof_date=asof_date)

    cost_totals = (
        costs.groupby("Asset", as_index=False)["Amount"]
        .sum()
        .rename(columns={"Amount": "Total Home Costs"})
    )
    inflow_totals = (
        inflows.groupby("Asset", as_index=False)["Amount"]
        .sum()
        .rename(columns={"Amount": "Total Inflows"})
    )

    mortgage_totals = (
        mortgages.groupby("Asset", as_index=False)
        .agg(
            {
                "Interest Paid": "sum",
                "Principal Repaid": "sum",
                "Outstanding Principal": "sum",
            }
        )
        .rename(
            columns={
                "Interest Paid": "Total Mortgage Interest",
                "Principal Repaid": "Total Mortgage Repayment",
                "Outstanding Principal": "Total Outstanding Mortgage",
            }
        )
    )

    if values.empty:
        value_totals = pd.DataFrame(columns=["Asset", "Current Property Value"])
    else:
        value_totals = (
            values.sort_values(by=["Asset", "Date"])
            .groupby("Asset", as_index=False)
            .tail(1)[["Asset", "Value"]]
            .rename(columns={"Value": "Current Property Value"})
        )

    summary = pd.merge(left=cost_totals, right=mortgage_totals, on="Asset", how="outer")
    summary = pd.merge(left=summary, right=inflow_totals, on="Asset", how="outer")
    summary = pd.merge(left=summary, right=value_totals, on="Asset", how="outer")

    if summary.empty:
        return pd.DataFrame(
            columns=[
                "Asset",
                "Total Home Costs",
                "Total Mortgage Interest",
                "Total Mortgage Repayment",
                "Total Inflows",
                "Net Cash Out",
                "Total Outstanding Mortgage",
                "Current Property Value",
                "Estimated Equity",
            ]
        )

    numeric_columns = [
        "Total Home Costs",
        "Total Mortgage Interest",
        "Total Mortgage Repayment",
        "Total Inflows",
        "Total Outstanding Mortgage",
        "Current Property Value",
    ]
    summary[numeric_columns] = summary[numeric_columns].apply(
        lambda col: pd.to_numeric(col, errors="coerce")
    )
    summary[numeric_columns] = summary[numeric_columns].fillna(0.0)
    summary["Net Cash Out"] = (
        summary["Total Home Costs"]
        + summary["Total Mortgage Interest"]
        + summary["Total Mortgage Repayment"]
        - summary["Total Inflows"]
    )
    summary["Estimated Equity"] = (
        summary["Current Property Value"] - summary["Total Outstanding Mortgage"]
    )

    summary = summary[
        [
            "Asset",
            "Total Home Costs",
            "Total Mortgage Interest",
            "Total Mortgage Repayment",
            "Total Inflows",
            "Net Cash Out",
            "Total Outstanding Mortgage",
            "Current Property Value",
            "Estimated Equity",
        ]
    ]

    numeric_output = [
        "Total Home Costs",
        "Total Mortgage Interest",
        "Total Mortgage Repayment",
        "Total Inflows",
        "Net Cash Out",
        "Total Outstanding Mortgage",
        "Current Property Value",
        "Estimated Equity",
    ]
    summary[numeric_output] = summary[numeric_output].round(2)
    return summary.sort_values(by="Asset").reset_index(drop=True)


if __name__ == "__main__":
    print(summarize_real_estate())
