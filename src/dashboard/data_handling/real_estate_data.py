from __future__ import annotations

from dataclasses import dataclass

import pandas as pd

from file_paths import REAL_ESTATE_FOLDER
from real_estate import (
    load_home_costs,
    load_home_inflows,
    load_home_values,
    load_mortgage_files,
)

INITIAL_PAYMENT_TYPE = "INITIAL_PAYMENT"
PAYMENT_ENTRY_TYPE = "PAYMENT"


@dataclass
class RealEstateDataBundle:
    costs: pd.DataFrame
    inflows: pd.DataFrame
    values: pd.DataFrame
    mortgages: pd.DataFrame
    errors: list[str]


def list_real_estate_assets() -> list[str]:
    """
    Lists configured real-estate assets based on folder names.

    returns:
        Sorted asset folder names.
    """
    if not REAL_ESTATE_FOLDER.exists():
        return []
    return sorted([path.name for path in REAL_ESTATE_FOLDER.iterdir() if path.is_dir()])


def _safe_loader_call(loader_name: str, load_fn, asof_date: str) -> tuple[pd.DataFrame, str | None]:
    """
    Executes a loader function and captures failures.

    args:
        loader_name: Name used in error messages.
        load_fn: Callable loader.
        asof_date: Date filter in YYYY-MM-DD.

    returns:
        Tuple of (frame, optional_error_message).
    """
    try:
        frame = load_fn(asof_date=asof_date)
        return frame, None
    except Exception as exc:
        return pd.DataFrame(), f"{loader_name}: {exc}"


def load_real_estate_bundle(asof_date: str) -> RealEstateDataBundle:
    """
    Loads all real-estate datasets for dashboard usage.

    args:
        asof_date: Date filter in YYYY-MM-DD.

    returns:
        Data bundle with optional loader errors.
    """
    errors: list[str] = []
    costs, costs_error = _safe_loader_call(
        loader_name="home costs", load_fn=load_home_costs, asof_date=asof_date
    )
    inflows, inflows_error = _safe_loader_call(
        loader_name="home inflows", load_fn=load_home_inflows, asof_date=asof_date
    )
    values, values_error = _safe_loader_call(
        loader_name="home values", load_fn=load_home_values, asof_date=asof_date
    )
    mortgages, mortgages_error = _safe_loader_call(
        loader_name="mortgages", load_fn=load_mortgage_files, asof_date=asof_date
    )

    for maybe_error in [costs_error, inflows_error, values_error, mortgages_error]:
        if maybe_error:
            errors.append(maybe_error)

    return RealEstateDataBundle(
        costs=costs,
        inflows=inflows,
        values=values,
        mortgages=mortgages,
        errors=errors,
    )


def filter_asset(frame: pd.DataFrame, asset: str) -> pd.DataFrame:
    """
    Filters frame to one asset unless ALL is selected.

    args:
        frame: Input data frame.
        asset: Asset name or ALL.

    returns:
        Filtered frame.
    """
    if frame.empty or asset == "ALL":
        return frame
    normalized_asset = str(asset).strip().lower()
    return frame[frame["Asset"].astype(str).str.strip().str.lower() == normalized_asset].copy()


def get_home_purchase_dates(costs: pd.DataFrame) -> list[pd.Timestamp]:
    """
    Extracts home-purchase dates based on initial payment rows.

    args:
        costs: Cost rows.

    returns:
        Sorted unique purchase dates.
    """
    if costs.empty:
        return []
    if "Cost Type" not in costs.columns:
        return []

    normalized_type = costs["Cost Type"].astype(str).str.strip().str.upper()
    purchase_rows = costs[normalized_type == INITIAL_PAYMENT_TYPE]
    if purchase_rows.empty:
        return []

    unique_dates = sorted(pd.to_datetime(purchase_rows["Date"]).dt.normalize().unique())
    return [pd.Timestamp(date_value) for date_value in unique_dates]


def summarize_mortgages_from_rows(mortgages: pd.DataFrame) -> pd.DataFrame:
    """
    Summarizes mortgage balances and payments from raw rows.

    args:
        mortgages: Mortgage transaction rows.

    returns:
        Per-mortgage summary.
    """
    output_columns = [
        "Asset",
        "Mortgage ID",
        "Initial Principal",
        "Interest Paid",
        "Principal Repaid",
        "Outstanding Principal",
        "Cash Out",
    ]
    if mortgages.empty:
        return pd.DataFrame(columns=output_columns)

    grouped = mortgages.groupby(["Asset", "Mortgage ID"], as_index=False).agg(
        {
            "Initial Principal": "sum",
            "Interest Paid": "sum",
            "Principal Repaid": "sum",
        }
    )
    grouped["Outstanding Principal"] = grouped["Initial Principal"] - grouped["Principal Repaid"]
    grouped["Cash Out"] = grouped["Interest Paid"] + grouped["Principal Repaid"]

    numeric_columns = [
        "Initial Principal",
        "Interest Paid",
        "Principal Repaid",
        "Outstanding Principal",
        "Cash Out",
    ]
    grouped[numeric_columns] = grouped[numeric_columns].round(2)
    return grouped[output_columns].sort_values(by=["Asset", "Mortgage ID"]).reset_index(drop=True)


def calculate_snapshot_metrics(
    costs: pd.DataFrame, inflows: pd.DataFrame, values: pd.DataFrame, mortgages: pd.DataFrame
) -> dict[str, float]:
    """
    Calculates point-in-time KPIs for summary cards.

    args:
        costs: Cost rows.
        inflows: Inflow rows.
        values: Valuation rows.
        mortgages: Mortgage rows.

    returns:
        KPI dictionary.
    """
    mortgage_summary = summarize_mortgages_from_rows(mortgages=mortgages)
    latest_value = 0.0
    if not values.empty:
        latest_values_per_asset = (
            values.sort_values(by=["Asset", "Date"]).groupby("Asset", as_index=False).tail(1)
        )
        latest_value = float(latest_values_per_asset["Value"].sum())

    total_costs = float(costs["Amount"].sum()) if not costs.empty else 0.0
    total_inflows = float(inflows["Amount"].sum()) if not inflows.empty else 0.0
    total_interest = (
        float(mortgage_summary["Interest Paid"].sum()) if not mortgage_summary.empty else 0.0
    )
    total_repaid = (
        float(mortgage_summary["Principal Repaid"].sum()) if not mortgage_summary.empty else 0.0
    )
    outstanding = (
        float(mortgage_summary["Outstanding Principal"].sum())
        if not mortgage_summary.empty
        else 0.0
    )
    net_cash_out = total_costs + total_interest + total_repaid - total_inflows
    estimated_equity = latest_value - outstanding

    return {
        "property_value": round(latest_value, 2),
        "outstanding_mortgage": round(outstanding, 2),
        "estimated_equity": round(estimated_equity, 2),
        "net_cash_out": round(net_cash_out, 2),
        "total_inflows": round(total_inflows, 2),
        "total_interest_paid": round(total_interest, 2),
        "total_principal_repaid": round(total_repaid, 2),
    }


def build_monthly_cashflow_frame(
    costs: pd.DataFrame, inflows: pd.DataFrame, mortgages: pd.DataFrame
) -> pd.DataFrame:
    """
    Builds a monthly cashflow frame for plotting.

    args:
        costs: Cost rows.
        inflows: Inflow rows.
        mortgages: Mortgage rows.

    returns:
        Monthly cashflow frame.
    """

    def _month_end(series: pd.Series) -> pd.Series:
        return series.dt.to_period("M").dt.to_timestamp(how="end").dt.normalize()

    date_parts: list[pd.Series] = []
    if not costs.empty:
        date_parts.append(costs["Date"])
    if not inflows.empty:
        date_parts.append(inflows["Date"])
    if not mortgages.empty:
        date_parts.append(mortgages["Date"])

    if not date_parts:
        return pd.DataFrame(
            columns=[
                "Date",
                "Home Costs",
                "Mortgage Interest",
                "Mortgage Repayment",
                "Inflows",
                "Net Cash Flow",
                "Cumulative Net Cash Flow",
            ]
        )

    min_date = pd.concat(date_parts).min().to_period("M").to_timestamp(how="end").normalize()
    max_date = pd.concat(date_parts).max().to_period("M").to_timestamp(how="end").normalize()
    month_index = pd.date_range(start=min_date, end=max_date, freq="ME")
    frame = pd.DataFrame({"Date": month_index})

    costs_without_initial = costs.copy()
    initial_payment_rows = costs.copy()
    if not costs_without_initial.empty:
        normalized_type = costs_without_initial["Cost Type"].astype(str).str.strip().str.upper()
        costs_without_initial = costs_without_initial[normalized_type != INITIAL_PAYMENT_TYPE]
        initial_payment_rows = initial_payment_rows[normalized_type == INITIAL_PAYMENT_TYPE]

    if costs_without_initial.empty:
        monthly_costs = pd.DataFrame(columns=["Date", "Home Costs"])
    else:
        monthly_costs = (
            costs_without_initial.assign(Date=_month_end(costs_without_initial["Date"]))
            .groupby("Date", as_index=False)["Amount"]
            .sum()
            .rename(columns={"Amount": "Home Costs"})
        )

    if initial_payment_rows.empty:
        monthly_initial_payments = pd.DataFrame(columns=["Date", "Initial Payments"])
    else:
        monthly_initial_payments = (
            initial_payment_rows.assign(Date=_month_end(initial_payment_rows["Date"]))
            .groupby("Date", as_index=False)["Amount"]
            .sum()
            .rename(columns={"Amount": "Initial Payments"})
        )

    if mortgages.empty:
        payment_rows = mortgages
    else:
        payment_rows = mortgages[mortgages["Entry Type"] == PAYMENT_ENTRY_TYPE].copy()
    if payment_rows.empty:
        monthly_mortgage = pd.DataFrame(columns=["Date", "Mortgage Interest", "Mortgage Repayment"])
    else:
        monthly_mortgage = (
            payment_rows.assign(Date=_month_end(payment_rows["Date"]))
            .groupby("Date", as_index=False)[["Interest Paid", "Principal Repaid"]]
            .sum()
            .rename(
                columns={
                    "Interest Paid": "Mortgage Interest",
                    "Principal Repaid": "Mortgage Repayment",
                }
            )
        )

    if inflows.empty:
        monthly_inflows = pd.DataFrame(columns=["Date", "Inflows"])
    else:
        monthly_inflows = (
            inflows.assign(Date=_month_end(inflows["Date"]))
            .groupby("Date", as_index=False)["Amount"]
            .sum()
            .rename(columns={"Amount": "Inflows"})
        )

    frame = pd.merge(left=frame, right=monthly_costs, on="Date", how="left")
    frame = pd.merge(left=frame, right=monthly_initial_payments, on="Date", how="left")
    frame = pd.merge(left=frame, right=monthly_mortgage, on="Date", how="left")
    frame = pd.merge(left=frame, right=monthly_inflows, on="Date", how="left")
    for column in [
        "Home Costs",
        "Initial Payments",
        "Mortgage Interest",
        "Mortgage Repayment",
        "Inflows",
    ]:
        frame[column] = frame[column].fillna(0.0)

    frame["Net Cash Flow"] = (
        frame["Inflows"]
        - frame["Home Costs"]
        - frame["Mortgage Interest"]
        - frame["Mortgage Repayment"]
    )
    frame["Cumulative Net Cash Flow"] = (
        frame["Net Cash Flow"] - frame["Initial Payments"]
    ).cumsum()
    return frame


def build_recent_outflows_frame(
    costs: pd.DataFrame, mortgages: pd.DataFrame, n: int | None = 5
) -> pd.DataFrame:
    """
    Builds a latest-outflows table frame.

    args:
        costs: Cost rows.
        mortgages: Mortgage rows.
        n: Number of final rows, or None for all rows.

    returns:
        Outflow rows sorted by most recent date.
    """
    parts: list[pd.DataFrame] = []

    if not costs.empty:
        cost_part = costs[["Date", "Asset", "Cost Type", "Amount"]].copy()
        cost_part = cost_part.rename(columns={"Cost Type": "Type"})
        cost_part["Type"] = "Cost: " + cost_part["Type"].astype(str)
        parts.append(cost_part[["Date", "Asset", "Type", "Amount"]])

    if not mortgages.empty:
        payment_rows = mortgages[mortgages["Entry Type"] == PAYMENT_ENTRY_TYPE].copy()
        if not payment_rows.empty:
            payment_rows["Amount"] = (
                payment_rows["Interest Paid"] + payment_rows["Principal Repaid"]
            )
            payment_rows["Type"] = "Mortgage: " + payment_rows["Mortgage ID"].astype(str)
            parts.append(payment_rows[["Date", "Asset", "Type", "Amount"]])

    if not parts:
        return pd.DataFrame(columns=["Date", "Asset", "Type", "Amount"])

    outflows = pd.concat(parts, ignore_index=True)
    outflows = outflows.sort_values(by=["Date", "Amount"], ascending=[False, False])
    if n is not None:
        outflows = outflows.head(n)
    return outflows.reset_index(drop=True)


def build_recent_inflows_frame(inflows: pd.DataFrame, n: int | None = 5) -> pd.DataFrame:
    """
    Builds a latest-inflows table frame.

    args:
        inflows: Inflow rows.
        n: Number of final rows, or None for all rows.

    returns:
        Inflow rows sorted by most recent date.
    """
    if inflows.empty:
        return pd.DataFrame(columns=["Date", "Asset", "Type", "Amount"])

    recent = inflows[["Date", "Asset", "Inflow Type", "Amount"]].copy()
    recent = recent.rename(columns={"Inflow Type": "Type"})
    recent = recent.sort_values(by=["Date", "Amount"], ascending=[False, False])
    if n is not None:
        recent = recent.head(n)
    return recent.reset_index(drop=True)


def build_mortgage_balance_frame(mortgages: pd.DataFrame) -> pd.DataFrame:
    """
    Builds mortgage outstanding balances by date and mortgage.

    args:
        mortgages: Mortgage rows.

    returns:
        Frame with per-mortgage and total outstanding balances.
    """
    if mortgages.empty:
        return pd.DataFrame(columns=["Date", "Mortgage ID", "Outstanding Principal"])

    lines: list[pd.DataFrame] = []
    for _, group in mortgages.groupby("Mortgage ID"):
        ordered = group.sort_values(by="Date").copy()
        ordered["Cumulative Repaid"] = ordered["Principal Repaid"].cumsum()
        ordered["Outstanding Principal"] = (
            ordered["Initial Principal"].sum() - ordered["Cumulative Repaid"]
        )
        lines.append(
            ordered[["Date", "Mortgage ID", "Outstanding Principal"]].drop_duplicates(
                subset=["Date"], keep="last"
            )
        )

    balance_raw = pd.concat(lines, ignore_index=True)
    all_dates = pd.Index(sorted(balance_raw["Date"].drop_duplicates()), name="Date")
    by_mortgage = (
        balance_raw.pivot_table(
            index="Date",
            columns="Mortgage ID",
            values="Outstanding Principal",
            aggfunc="last",
        )
        .reindex(all_dates)
        .sort_index()
    )
    by_mortgage = by_mortgage.ffill().fillna(0.0)
    balance = (
        by_mortgage.stack()
        .rename("Outstanding Principal")
        .reset_index()
        .rename(columns={"level_1": "Mortgage ID"})
    )
    total = by_mortgage.sum(axis=1).rename("Outstanding Principal").reset_index()
    total["Mortgage ID"] = "TOTAL"
    total = total[["Date", "Mortgage ID", "Outstanding Principal"]]

    return (
        pd.concat([balance, total], ignore_index=True)
        .sort_values(by=["Date", "Mortgage ID"])
        .reset_index(drop=True)
    )


def build_value_equity_frame(
    values: pd.DataFrame, mortgages: pd.DataFrame, asof_date: str
) -> pd.DataFrame:
    """
    Builds the property value versus equity timeline.

    args:
        values: Valuation rows.
        mortgages: Mortgage rows.
        asof_date: Date filter in YYYY-MM-DD.

    returns:
        Date-level frame with value, outstanding and equity.
    """

    def _month_end_ts(timestamp: pd.Timestamp) -> pd.Timestamp:
        return timestamp.to_period("M").to_timestamp(how="end").normalize()

    if values.empty:
        return pd.DataFrame(
            columns=["Date", "Property Value", "Outstanding Mortgage", "Estimated Equity"]
        )

    asof_timestamp = pd.to_datetime(asof_date)
    month_end_dates = [_month_end_ts(values["Date"].min())]
    if not mortgages.empty:
        month_end_dates.append(_month_end_ts(mortgages["Date"].min()))
    start_date = min(month_end_dates)
    end_date = _month_end_ts(asof_timestamp)

    month_index = pd.date_range(start=start_date, end=end_date, freq="ME")
    value_dates = list(month_index)
    normalized_asof = asof_timestamp.normalize()
    if not value_dates or value_dates[-1] != normalized_asof:
        value_dates.append(normalized_asof)
    value_frame = pd.DataFrame({"Date": sorted(pd.to_datetime(value_dates).unique())})

    value_series = values.sort_values(by=["Asset", "Date"]).copy()

    asset_values: list[pd.DataFrame] = []
    for asset_name, group in value_series.groupby("Asset"):
        asset_group = group.sort_values(by="Date")[["Date", "Value"]].drop_duplicates(
            subset=["Date"], keep="last"
        )
        merged = pd.merge_asof(
            left=value_frame.sort_values(by="Date"),
            right=asset_group.sort_values(by="Date"),
            on="Date",
            direction="backward",
        )
        merged = merged.rename(columns={"Value": asset_name})
        asset_values.append(merged[["Date", asset_name]])

    combined_values = value_frame.copy()
    for asset_value in asset_values:
        combined_values = pd.merge(left=combined_values, right=asset_value, on="Date", how="left")
    combined_values = combined_values.ffill().fillna(0.0)
    combined_values["Property Value"] = combined_values.drop(columns=["Date"]).sum(axis=1)

    balance = build_mortgage_balance_frame(mortgages=mortgages)
    if balance.empty:
        combined_values["Outstanding Mortgage"] = 0.0
    else:
        total_balance = (
            balance[balance["Mortgage ID"] == "TOTAL"][["Date", "Outstanding Principal"]]
            .sort_values(by="Date")
            .drop_duplicates(subset=["Date"], keep="last")
        )
        combined_values = pd.merge_asof(
            left=combined_values.sort_values(by="Date"),
            right=total_balance,
            on="Date",
            direction="backward",
        )
        combined_values = combined_values.rename(
            columns={"Outstanding Principal": "Outstanding Mortgage"}
        )
        combined_values["Outstanding Mortgage"] = combined_values["Outstanding Mortgage"].fillna(
            0.0
        )

    combined_values["Estimated Equity"] = (
        combined_values["Property Value"] - combined_values["Outstanding Mortgage"]
    )
    return combined_values[["Date", "Property Value", "Outstanding Mortgage", "Estimated Equity"]]
