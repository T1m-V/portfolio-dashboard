from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import pandas as pd
from portfolio_core import active_context

COST_COLUMNS = ["Asset", "Date", "Cost Type", "Amount", "Notes"]
INFLOW_COLUMNS = ["Asset", "Date", "Inflow Type", "Amount", "Notes"]
VALUE_COLUMNS = ["Asset", "Date", "Value", "Valuation Type", "Notes"]
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
OWNERSHIP_COLUMNS = ["Scope", "Identifier", "Ownership Share", "Notes"]
MORTGAGE_VALUE_COLUMNS = ["Initial Principal", "Interest Paid", "Principal Repaid"]


@dataclass(slots=True)
class RealEstateData:
    costs: pd.DataFrame
    inflows: pd.DataFrame
    values: pd.DataFrame
    mortgages: pd.DataFrame

    def period(self, from_date: str, through_date: str) -> RealEstateData:
        start, end = pd.Timestamp(from_date), pd.Timestamp(through_date)

        def select(frame: pd.DataFrame) -> pd.DataFrame:
            return frame[frame["Date"].between(start, end)].copy()

        return RealEstateData(
            costs=select(self.costs),
            inflows=select(self.inflows),
            values=select(self.values),
            mortgages=select(self.mortgages),
        )


def empty_real_estate_data() -> RealEstateData:
    return RealEstateData(
        costs=pd.DataFrame(columns=COST_COLUMNS),
        inflows=pd.DataFrame(columns=INFLOW_COLUMNS),
        values=pd.DataFrame(columns=VALUE_COLUMNS),
        mortgages=pd.DataFrame(columns=MORTGAGE_COLUMNS),
    )


def _read_csv(path: Path, columns: list[str], numeric: list[str]) -> pd.DataFrame:
    frame = pd.read_csv(path)
    if list(frame.columns) != columns:
        raise ValueError(
            f"Invalid real-estate schema for {path.name}: "
            f"expected {columns}, got {list(frame.columns)}"
        )
    frame["Date"] = pd.to_datetime(frame["Date"], format="%Y-%m-%d")
    for column in numeric:
        frame[column] = pd.to_numeric(frame[column])
    for column in set(columns) - {"Date", *numeric}:
        frame[column] = frame[column].fillna("").astype(str).str.strip()
    return frame


def _ownership(folder: Path) -> tuple[float, dict[str, float]]:
    path = folder / "ownership.csv"
    if not path.exists():
        return 1.0, {}

    frame = pd.read_csv(path)
    if list(frame.columns) != OWNERSHIP_COLUMNS:
        raise ValueError(
            f"Invalid real-estate schema for {path.name}: "
            f"expected {OWNERSHIP_COLUMNS}, got {list(frame.columns)}"
        )
    frame["Scope"] = frame["Scope"].astype(str).str.strip().str.upper()
    frame["Identifier"] = frame["Identifier"].astype(str).str.strip()
    frame["Ownership Share"] = pd.to_numeric(frame["Ownership Share"])
    if not frame["Scope"].isin({"ASSET", "MORTGAGE"}).all():
        raise ValueError(f"{path.name} Scope must be ASSET or MORTGAGE")
    if not ((frame["Ownership Share"] > 0) & (frame["Ownership Share"] <= 1)).all():
        raise ValueError(f"{path.name} Ownership Share must be in (0, 1]")

    assets = frame[frame["Scope"] == "ASSET"]
    if len(assets) > 1:
        raise ValueError(f"{path.name} may contain only one ASSET row")
    asset_share = float(assets.iloc[0]["Ownership Share"]) if not assets.empty else 1.0

    mortgages = frame[frame["Scope"] == "MORTGAGE"].copy()
    mortgages["key"] = mortgages["Identifier"].str.casefold()
    if mortgages["key"].eq("").any() or mortgages["key"].duplicated().any():
        raise ValueError(f"{path.name} mortgage identifiers must be non-empty and unique")
    return asset_share, dict(zip(mortgages["key"], mortgages["Ownership Share"], strict=True))


def _validate_asset(frame: pd.DataFrame, folder: Path) -> None:
    if frame.empty:
        return
    assets = frame["Asset"].str.casefold().unique()
    if len(assets) != 1 or assets[0] != folder.name.casefold():
        raise ValueError(f"Rows in {folder.name} must use that folder name as Asset")


def _load_optional(
    folder: Path,
    filename: str,
    columns: list[str],
    numeric: list[str],
    share: float,
) -> pd.DataFrame | None:
    path = folder / filename
    if not path.exists():
        return None
    frame = _read_csv(path, columns, numeric)
    _validate_asset(frame, folder)
    frame[numeric] = frame[numeric] * share
    return frame


def _validate_mortgage(frame: pd.DataFrame, path: Path) -> None:
    if frame.empty or frame.iloc[0]["Entry Type"] != "ORIGINATION":
        raise ValueError(f"{path.name} must start with an ORIGINATION row")
    payments = frame.iloc[1:]
    if not payments["Entry Type"].eq("PAYMENT").all():
        raise ValueError(f"Rows after ORIGINATION in {path.name} must be PAYMENT rows")
    if frame.iloc[0]["Initial Principal"] == 0 or not payments["Initial Principal"].eq(0).all():
        raise ValueError(f"{path.name} has an invalid Initial Principal")


def _concat(frames: list[pd.DataFrame], columns: list[str]) -> pd.DataFrame:
    return pd.concat(frames, ignore_index=True) if frames else pd.DataFrame(columns=columns)


def load_real_estate_data(as_of_date: str) -> RealEstateData:
    root = active_context().paths.real_estate
    if not root.exists():
        return empty_real_estate_data()

    cutoff = pd.Timestamp(as_of_date)
    costs: list[pd.DataFrame] = []
    inflows: list[pd.DataFrame] = []
    values: list[pd.DataFrame] = []
    mortgages: list[pd.DataFrame] = []
    for folder in sorted(path for path in root.iterdir() if path.is_dir()):
        asset_share, mortgage_shares = _ownership(folder)
        for target, filename, columns, numeric in (
            (costs, "costs.csv", COST_COLUMNS, ["Amount"]),
            (inflows, "inflows.csv", INFLOW_COLUMNS, ["Amount"]),
            (values, "values.csv", VALUE_COLUMNS, ["Value"]),
        ):
            frame = _load_optional(folder, filename, columns, numeric, asset_share)
            if frame is not None:
                target.append(frame[frame["Date"] <= cutoff])

        for path in sorted(folder.glob("*mortgage*.csv")):
            frame = _read_csv(path, MORTGAGE_COLUMNS, MORTGAGE_VALUE_COLUMNS)
            _validate_asset(frame, folder)
            _validate_mortgage(frame, path)
            shares = frame["Mortgage ID"].str.casefold().map(mortgage_shares).fillna(asset_share)
            frame[MORTGAGE_VALUE_COLUMNS] = frame[MORTGAGE_VALUE_COLUMNS].mul(shares, axis=0)
            mortgages.append(frame[frame["Date"] <= cutoff])

    return RealEstateData(
        costs=_concat(costs, COST_COLUMNS),
        inflows=_concat(inflows, INFLOW_COLUMNS),
        values=_concat(values, VALUE_COLUMNS),
        mortgages=_concat(mortgages, MORTGAGE_COLUMNS),
    )


def mortgage_summary(mortgages: pd.DataFrame) -> pd.DataFrame:
    columns = [
        "Mortgage ID",
        "Initial Principal",
        "Interest Paid",
        "Principal Repaid",
        "Outstanding Principal",
    ]
    if mortgages.empty:
        return pd.DataFrame(columns=columns)
    result = mortgages.groupby("Mortgage ID", as_index=False)[MORTGAGE_VALUE_COLUMNS].sum()
    result["Outstanding Principal"] = result["Initial Principal"] - result["Principal Repaid"]
    return result[columns].round(2)


def snapshot_metrics(data: RealEstateData) -> dict[str, float]:
    summary = mortgage_summary(data.mortgages)
    latest_values = (
        data.values.sort_values(["Asset", "Date"]).groupby("Asset").tail(1)
        if not data.values.empty
        else data.values
    )
    property_value = float(latest_values["Value"].sum()) if not latest_values.empty else 0.0
    outstanding = float(summary["Outstanding Principal"].sum()) if not summary.empty else 0.0
    return {
        "property_value": property_value,
        "outstanding_mortgage": outstanding,
        "estimated_equity": property_value - outstanding,
    }


def period_net_cash_out(data: RealEstateData) -> float:
    costs = float(data.costs["Amount"].sum()) if not data.costs.empty else 0.0
    inflows = float(data.inflows["Amount"].sum()) if not data.inflows.empty else 0.0
    if data.mortgages.empty:
        mortgage = 0.0
    else:
        payments = data.mortgages[data.mortgages["Entry Type"] == "PAYMENT"]
        mortgage = float(payments[["Interest Paid", "Principal Repaid"]].sum().sum())
    return round(costs + mortgage - inflows, 2)


def monthly_cashflow(data: RealEstateData) -> pd.DataFrame:
    columns = [
        "Date",
        "Home Costs",
        "Mortgage Interest",
        "Mortgage Repayment",
        "Inflows",
        "Cumulative Net Cash Flow",
    ]
    dated = [frame for frame in (data.costs, data.inflows, data.mortgages) if not frame.empty]
    if not dated:
        return pd.DataFrame(columns=columns)

    dates = pd.concat([frame["Date"] for frame in dated])
    index = pd.date_range(
        dates.min().to_period("M").end_time.normalize(),
        dates.max().to_period("M").end_time.normalize(),
        freq="ME",
    )
    monthly = pd.DataFrame(index=index)

    def totals(frame: pd.DataFrame, value: str, mask: pd.Series | None = None) -> pd.Series:
        if frame.empty:
            return pd.Series(dtype=float)
        selected = frame if mask is None else frame[mask]
        result = selected.groupby(selected["Date"].dt.to_period("M"))[value].sum()
        result.index = result.index.to_timestamp(how="end").normalize()
        return result

    cost_types = data.costs["Cost Type"] if not data.costs.empty else pd.Series(dtype=str)
    monthly["Home Costs"] = totals(data.costs, "Amount", cost_types != "INITIAL_PAYMENT")
    initial = totals(data.costs, "Amount", cost_types == "INITIAL_PAYMENT")
    payments = (
        data.mortgages["Entry Type"] == "PAYMENT"
        if not data.mortgages.empty
        else pd.Series(dtype=bool)
    )
    monthly["Mortgage Interest"] = totals(data.mortgages, "Interest Paid", payments)
    monthly["Mortgage Repayment"] = totals(data.mortgages, "Principal Repaid", payments)
    monthly["Inflows"] = totals(data.inflows, "Amount")
    monthly = monthly.fillna(0.0)
    monthly["Cumulative Net Cash Flow"] = (
        monthly["Inflows"]
        - monthly["Home Costs"]
        - monthly["Mortgage Interest"]
        - monthly["Mortgage Repayment"]
        - initial.reindex(monthly.index, fill_value=0)
    ).cumsum()
    return monthly.reset_index(names="Date")[columns]


def mortgage_balances(mortgages: pd.DataFrame) -> pd.DataFrame:
    columns = ["Date", "Mortgage ID", "Outstanding Principal"]
    if mortgages.empty:
        return pd.DataFrame(columns=columns)
    histories = []
    for mortgage_id, rows in mortgages.groupby("Mortgage ID"):
        rows = rows.sort_values("Date").copy()
        rows["Outstanding Principal"] = (
            rows["Initial Principal"].sum() - rows["Principal Repaid"].cumsum()
        )
        rows["Mortgage ID"] = mortgage_id
        histories.append(rows[columns].drop_duplicates("Date", keep="last"))

    events = pd.concat(histories)
    pivot = events.pivot(index="Date", columns="Mortgage ID", values="Outstanding Principal")
    pivot = pivot.sort_index().ffill().fillna(0.0)
    result = pivot.stack().rename("Outstanding Principal").reset_index()
    totals = pivot.sum(axis=1).rename("Outstanding Principal").reset_index()
    totals["Mortgage ID"] = "TOTAL"
    return pd.concat([result, totals[columns]], ignore_index=True).sort_values(columns[:2])


def value_equity(data: RealEstateData, as_of_date: str) -> pd.DataFrame:
    columns = ["Date", "Property Value", "Outstanding Mortgage", "Estimated Equity"]
    if data.values.empty:
        return pd.DataFrame(columns=columns)

    as_of = pd.Timestamp(as_of_date)
    starts = [data.values["Date"].min()]
    if not data.mortgages.empty:
        starts.append(data.mortgages["Date"].min())
    dates = list(pd.date_range(min(starts), as_of, freq="ME"))
    if not dates or dates[-1] != as_of:
        dates.append(as_of)
    result = pd.DataFrame({"Date": sorted(set(dates))})

    asset_columns = []
    for asset, rows in data.values.groupby("Asset"):
        asset_columns.append(asset)
        history = rows.sort_values("Date")[["Date", "Value"]].drop_duplicates("Date", keep="last")
        result = pd.merge_asof(result, history.rename(columns={"Value": asset}), on="Date")
    result["Property Value"] = result[asset_columns].fillna(0.0).sum(axis=1)

    balances = mortgage_balances(data.mortgages)
    if balances.empty:
        result["Outstanding Mortgage"] = 0.0
    else:
        total = balances[balances["Mortgage ID"] == "TOTAL"].drop(columns="Mortgage ID")
        result = pd.merge_asof(result, total.sort_values("Date"), on="Date")
        result = result.rename(columns={"Outstanding Principal": "Outstanding Mortgage"})
        result["Outstanding Mortgage"] = result["Outstanding Mortgage"].fillna(0.0)
    result["Estimated Equity"] = result["Property Value"] - result["Outstanding Mortgage"]
    return result[columns]


def recent_cashflows(data: RealEstateData, limit: int = 5) -> tuple[pd.DataFrame, pd.DataFrame]:
    columns = ["Date", "Type", "Amount"]
    outflows = []
    if not data.costs.empty:
        costs = data.costs[["Date", "Cost Type", "Amount"]].rename(columns={"Cost Type": "Type"})
        costs["Type"] = "Cost: " + costs["Type"]
        outflows.append(costs)
    if not data.mortgages.empty:
        payments = data.mortgages[data.mortgages["Entry Type"] == "PAYMENT"].copy()
        payments["Type"] = "Mortgage: " + payments["Mortgage ID"]
        payments["Amount"] = payments["Interest Paid"] + payments["Principal Repaid"]
        outflows.append(payments[columns])
    outflow = (
        pd.concat(outflows).sort_values("Date", ascending=False).head(limit).reset_index(drop=True)
        if outflows
        else pd.DataFrame(columns=columns)
    )
    inflow = (
        data.inflows[["Date", "Inflow Type", "Amount"]]
        .rename(columns={"Inflow Type": "Type"})
        .sort_values("Date", ascending=False)
        .head(limit)
        .reset_index(drop=True)
        if not data.inflows.empty
        else pd.DataFrame(columns=columns)
    )
    return outflow, inflow
