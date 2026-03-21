import pandas as pd

from dashboard.data_handling.real_estate_data import build_mortgage_balance_frame


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
