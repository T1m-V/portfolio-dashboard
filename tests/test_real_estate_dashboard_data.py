import pandas as pd

from dashboard.data_handling.real_estate_data import (
    build_monthly_cashflow_frame,
    build_mortgage_balance_frame,
    build_value_equity_frame,
    calculate_snapshot_metrics,
)


def test_mortgage_total_carries_forward_between_payment_dates() -> None:
    mortgages = pd.DataFrame(
        [
            ["Donau87", "M1", "2024-12-09", "ORIGINATION", 100.0, 0.0, 0.0, ""],
            ["Donau87", "M1", "2025-01-01", "PAYMENT", 0.0, 1.0, 10.0, ""],
            ["Donau87", "M2", "2024-12-09", "ORIGINATION", 50.0, 0.0, 0.0, ""],
            ["Donau87", "M2", "2025-01-09", "PAYMENT", 0.0, 1.0, 5.0, ""],
        ],
        columns=[
            "Asset",
            "Mortgage ID",
            "Date",
            "Entry Type",
            "Initial Principal",
            "Interest Paid",
            "Principal Repaid",
            "Notes",
        ],
    )
    mortgages["Date"] = pd.to_datetime(mortgages["Date"])

    balance = build_mortgage_balance_frame(mortgages=mortgages)
    total = (
        balance[balance["Mortgage ID"] == "TOTAL"][["Date", "Outstanding Principal"]]
        .sort_values(by="Date")
        .reset_index(drop=True)
    )

    totals_by_date = {
        row["Date"].strftime("%Y-%m-%d"): round(float(row["Outstanding Principal"]), 2)
        for _, row in total.iterrows()
    }

    assert totals_by_date["2024-12-09"] == 150.00
    assert totals_by_date["2025-01-01"] == 140.00
    assert totals_by_date["2025-01-09"] == 135.00


def test_dashboard_computations_align_for_metrics_cashflow_and_equity() -> None:
    costs = pd.DataFrame(
        [
            ["Donau87", "2025-01-05", "INITIAL_PAYMENT", 1000.0, "Down payment"],
            ["Donau87", "2025-02-10", "MAINTENANCE", 200.0, "Repairs"],
        ],
        columns=["Asset", "Date", "Cost Type", "Amount", "Notes"],
    )
    inflows = pd.DataFrame(
        [["Donau87", "2025-02-20", "AVOIDED_RENT", 50.0, "Saved rent"]],
        columns=["Asset", "Date", "Inflow Type", "Amount", "Notes"],
    )
    values = pd.DataFrame(
        [
            ["Donau87", "2025-01-01", 10000.0, "WOZ", "WOZ 2025"],
            ["Donau87", "2025-03-01", 11000.0, "WOZ", "WOZ update"],
        ],
        columns=["Asset", "Date", "Value", "Valuation Type", "Notes"],
    )
    mortgages = pd.DataFrame(
        [
            ["Donau87", "M1", "2025-01-01", "ORIGINATION", 6000.0, 0.0, 0.0, "Origination"],
            ["Donau87", "M1", "2025-02-01", "PAYMENT", 0.0, 30.0, 100.0, "Payment"],
        ],
        columns=[
            "Asset",
            "Mortgage ID",
            "Date",
            "Entry Type",
            "Initial Principal",
            "Interest Paid",
            "Principal Repaid",
            "Notes",
        ],
    )

    for frame in [costs, inflows, values, mortgages]:
        frame["Date"] = pd.to_datetime(frame["Date"])

    metrics = calculate_snapshot_metrics(
        costs=costs, inflows=inflows, values=values, mortgages=mortgages
    )
    assert metrics == {
        "property_value": 11000.0,
        "outstanding_mortgage": 5900.0,
        "estimated_equity": 5100.0,
        "net_cash_out": 1280.0,
        "total_inflows": 50.0,
        "total_interest_paid": 30.0,
        "total_principal_repaid": 100.0,
    }

    monthly_cashflow = build_monthly_cashflow_frame(
        costs=costs, inflows=inflows, mortgages=mortgages
    )
    cashflow_by_date = {
        row["Date"].strftime("%Y-%m-%d"): (
            round(float(row["Net Cash Flow"]), 2),
            round(float(row["Cumulative Net Cash Flow"]), 2),
        )
        for _, row in monthly_cashflow.iterrows()
    }
    assert cashflow_by_date == {
        "2025-01-31": (0.0, -1000.0),
        "2025-02-28": (-280.0, -1280.0),
    }

    value_equity = build_value_equity_frame(
        values=values, mortgages=mortgages, asof_date="2025-03-15"
    )
    equity_by_date = {
        row["Date"].strftime("%Y-%m-%d"): (
            round(float(row["Property Value"]), 2),
            round(float(row["Outstanding Mortgage"]), 2),
            round(float(row["Estimated Equity"]), 2),
        )
        for _, row in value_equity.iterrows()
    }
    assert equity_by_date == {
        "2025-01-31": (10000.0, 6000.0, 4000.0),
        "2025-02-28": (10000.0, 5900.0, 4100.0),
        "2025-03-15": (11000.0, 5900.0, 5100.0),
        "2025-03-31": (11000.0, 5900.0, 5100.0),
    }


def test_dashboard_helpers_empty_state_contracts() -> None:
    empty = pd.DataFrame()

    metrics = calculate_snapshot_metrics(costs=empty, inflows=empty, values=empty, mortgages=empty)
    assert metrics == {
        "property_value": 0.0,
        "outstanding_mortgage": 0.0,
        "estimated_equity": 0.0,
        "net_cash_out": 0.0,
        "total_inflows": 0.0,
        "total_interest_paid": 0.0,
        "total_principal_repaid": 0.0,
    }

    monthly_cashflow = build_monthly_cashflow_frame(costs=empty, inflows=empty, mortgages=empty)
    assert monthly_cashflow.empty
    assert list(monthly_cashflow.columns) == [
        "Date",
        "Home Costs",
        "Mortgage Interest",
        "Mortgage Repayment",
        "Inflows",
        "Net Cash Flow",
        "Cumulative Net Cash Flow",
    ]

    mortgage_balance = build_mortgage_balance_frame(mortgages=empty)
    assert mortgage_balance.empty
    assert list(mortgage_balance.columns) == ["Date", "Mortgage ID", "Outstanding Principal"]

    value_equity = build_value_equity_frame(values=empty, mortgages=empty, asof_date="2026-12-31")
    assert value_equity.empty
    assert list(value_equity.columns) == [
        "Date",
        "Property Value",
        "Outstanding Mortgage",
        "Estimated Equity",
    ]
