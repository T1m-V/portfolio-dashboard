from pathlib import Path

import pandas as pd
import pytest
from portfolio_core import active_context

from portfolio_dashboard.real_estate import (
    COST_COLUMNS,
    INFLOW_COLUMNS,
    MORTGAGE_COLUMNS,
    OWNERSHIP_COLUMNS,
    VALUE_COLUMNS,
    load_real_estate_data,
)
from portfolio_dashboard.services import build_real_estate_payload


def write_csv(path: Path, columns: list[str], rows: list[list[object]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    pd.DataFrame(rows, columns=columns).to_csv(path, index=False)


def seed_real_estate() -> Path:
    folder = active_context().paths.real_estate / "house"
    write_csv(
        folder / "ownership.csv",
        OWNERSHIP_COLUMNS,
        [["ASSET", "House", 0.5, ""], ["MORTGAGE", "M2", 1.0, ""]],
    )
    write_csv(
        folder / "costs.csv",
        COST_COLUMNS,
        [
            ["House", "2025-01-01", "INITIAL_PAYMENT", 1000, ""],
            ["House", "2025-02-10", "MAINTENANCE", 200, ""],
        ],
    )
    write_csv(
        folder / "inflows.csv",
        INFLOW_COLUMNS,
        [["House", "2025-02-20", "AVOIDED_RENT", 100, ""]],
    )
    write_csv(
        folder / "values.csv",
        VALUE_COLUMNS,
        [["House", "2025-01-01", 10000, "WOZ", ""]],
    )
    write_csv(
        folder / "mortgage_m1.csv",
        MORTGAGE_COLUMNS,
        [
            ["House", "M1", "2025-01-01", "ORIGINATION", 6000, 0, 0, ""],
            ["House", "M1", "2025-02-01", "PAYMENT", 0, 30, 100, ""],
        ],
    )
    write_csv(
        folder / "mortgage_m2.csv",
        MORTGAGE_COLUMNS,
        [
            ["House", "M2", "2025-01-01", "ORIGINATION", 1000, 0, 0, ""],
            ["House", "M2", "2025-03-01", "PAYMENT", 0, 10, 100, ""],
        ],
    )
    return folder


def test_real_estate_is_loaded_once_with_ownership_and_dashboard_calculations() -> None:
    seed_real_estate()
    payload = build_real_estate_payload(selected_date="2025-03-31", from_date="2025-02-01")
    metrics = {metric["label"]: metric["value"] for metric in payload["metrics"]}
    assert metrics == {
        "Property Value": 5000.0,
        "Outstanding Mortgage": 3850.0,
        "Estimated Equity": 1150.0,
        "Net Cash Out": 225.0,
    }
    assert payload["startDate"] == "2025-01-01"
    assert len(payload["mortgages"]["rows"]) == 2
    assert payload["mortgageBalances"][-1]["Outstanding Principal"] == 3850.0
    assert {row["label"] for row in payload["outflows"]} == {
        "Cost: MAINTENANCE",
        "Mortgage Interest",
        "Mortgage Repayment",
    }


def test_real_estate_rejects_schema_drift() -> None:
    folder = active_context().paths.real_estate / "house"
    write_csv(folder / "costs.csv", ["Asset", "Date", "Amount"], [])
    with pytest.raises(ValueError, match="Invalid real-estate schema"):
        load_real_estate_data("2025-01-01")


def test_absent_real_estate_data_is_a_useful_empty_payload() -> None:
    payload = build_real_estate_payload(selected_date="2025-03-31", from_date="2025-02-01")
    assert [metric["value"] for metric in payload["metrics"]] == [0.0, 0.0, 0.0, 0.0]
    assert payload["valueEquity"] == []
    assert payload["mortgages"] == {
        "columns": [
            "Mortgage ID",
            "Initial Principal",
            "Interest Paid",
            "Principal Repaid",
            "Outstanding Principal",
        ],
        "rows": [],
    }
