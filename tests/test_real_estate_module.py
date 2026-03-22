from pathlib import Path

import pandas as pd
import pytest

import real_estate.core as real_estate_core
from real_estate import (
    load_home_costs,
    load_home_inflows,
    load_home_values,
    load_mortgage_files,
    summarize_mortgages,
    summarize_real_estate,
)


def _write_csv(path: Path, columns: list[str], rows: list[list[object]]) -> None:
    frame = pd.DataFrame(rows, columns=columns)
    path.parent.mkdir(parents=True, exist_ok=True)
    frame.to_csv(path, index=False)


@pytest.fixture
def real_estate_paths(tmp_path, monkeypatch):
    folder = tmp_path / "real_estate"
    asset_folder = folder / "donau87"
    costs_path = asset_folder / "costs.csv"
    inflows_path = asset_folder / "inflows.csv"
    values_path = asset_folder / "values.csv"
    ownership_path = asset_folder / "ownership.csv"

    monkeypatch.setattr(real_estate_core, "REAL_ESTATE_FOLDER", folder)

    return {
        "folder": folder,
        "asset_folder": asset_folder,
        "costs_path": costs_path,
        "inflows_path": inflows_path,
        "values_path": values_path,
        "ownership_path": ownership_path,
    }


def _seed_valid_files(
    asset_folder: Path, costs_path: Path, inflows_path: Path, values_path: Path
) -> None:
    _write_csv(
        path=costs_path,
        columns=["Asset", "Date", "Cost Type", "Amount", "Notes"],
        rows=[
            ["Donau87", "2024-05-01", "INITIAL_PAYMENT", 25000, "Down payment"],
            ["Donau87", "2025-01-10", "OZB", 1500, "Annual tax"],
            ["Donau87", "2025-07-01", "MAINTENANCE", 700, "Repairs"],
        ],
    )
    _write_csv(
        path=inflows_path,
        columns=["Asset", "Date", "Inflow Type", "Amount", "Notes"],
        rows=[
            ["Donau87", "2026-01-01", "AVOIDED_RENT", 1400, "Saved rent"],
            ["Donau87", "2026-02-01", "AVOIDED_RENT", 1400, "Saved rent"],
        ],
    )
    _write_csv(
        path=asset_folder / "mortgage_abn.csv",
        columns=real_estate_core.MORTGAGE_COLUMNS,
        rows=[
            ["Donau87", "DONAU87_M1", "2024-05-01", "ORIGINATION", 300000, 0, 0, "Origination"],
            ["Donau87", "DONAU87_M1", "2026-01-01", "PAYMENT", 0, 800, 1000, "Jan payment"],
            ["Donau87", "DONAU87_M1", "2026-02-01", "PAYMENT", 0, 790, 1000, "Feb payment"],
        ],
    )
    _write_csv(
        path=asset_folder / "mortgage_renske.csv",
        columns=real_estate_core.MORTGAGE_COLUMNS,
        rows=[
            ["Donau87", "DONAU87_M2", "2024-05-01", "ORIGINATION", 100000, 0, 0, "Origination"],
            ["Donau87", "DONAU87_M2", "2026-01-01", "PAYMENT", 0, 250, 300, "Jan payment"],
            ["Donau87", "DONAU87_M2", "2026-02-01", "PAYMENT", 0, 249, 300, "Feb payment"],
        ],
    )
    _write_csv(
        path=values_path,
        columns=real_estate_core.VALUE_COLUMNS,
        rows=[
            ["Donau87", "2024-12-09", 561000, "WOZ", "Purchase valuation"],
            ["Donau87", "2025-01-01", 561000, "WOZ", "WOZ 2025"],
            ["Donau87", "2026-01-01", 558000, "WOZ", "WOZ 2026"],
        ],
    )


def test_loaders_enforce_canonical_columns(real_estate_paths) -> None:
    _seed_valid_files(
        asset_folder=real_estate_paths["asset_folder"],
        costs_path=real_estate_paths["costs_path"],
        inflows_path=real_estate_paths["inflows_path"],
        values_path=real_estate_paths["values_path"],
    )

    costs = load_home_costs()
    inflows = load_home_inflows()
    values = load_home_values()
    mortgages = load_mortgage_files()

    assert list(costs.columns) == real_estate_core.COST_COLUMNS
    assert list(inflows.columns) == real_estate_core.INFLOW_COLUMNS
    assert list(values.columns) == real_estate_core.VALUE_COLUMNS
    assert list(mortgages.columns) == real_estate_core.MORTGAGE_COLUMNS
    assert pd.api.types.is_datetime64_any_dtype(costs["Date"])
    assert pd.api.types.is_datetime64_any_dtype(inflows["Date"])
    assert pd.api.types.is_datetime64_any_dtype(values["Date"])
    assert pd.api.types.is_datetime64_any_dtype(mortgages["Date"])


@pytest.mark.parametrize(
    ("case_name", "expected_pattern"),
    [
        ("invalid_asof_date", "Invalid asof_date"),
        ("schema_mismatch", "Invalid CSV schema"),
        ("invalid_date_value", "Invalid date value"),
        ("invalid_numeric_sign", "must be positive"),
    ],
)
def test_loader_validation_errors_parametrized(
    real_estate_paths, case_name: str, expected_pattern: str
) -> None:
    if case_name == "invalid_asof_date":
        with pytest.raises(ValueError, match=expected_pattern):
            load_home_costs(asof_date="2026-31-12")
        return

    if case_name == "schema_mismatch":
        _write_csv(
            path=real_estate_paths["costs_path"],
            columns=["Asset", "Date", "Cost Type", "Amount"],
            rows=[["Donau87", "2026-01-01", "MAINTENANCE", 200]],
        )
        with pytest.raises(ValueError, match=expected_pattern):
            load_home_costs(asof_date="2026-12-31")
        return

    if case_name == "invalid_date_value":
        _write_csv(
            path=real_estate_paths["inflows_path"],
            columns=real_estate_core.INFLOW_COLUMNS,
            rows=[["Donau87", "2026-13-01", "AVOIDED_RENT", 1400, "Invalid month"]],
        )
        with pytest.raises(ValueError, match=expected_pattern):
            load_home_inflows(asof_date="2026-12-31")
        return

    if case_name == "invalid_numeric_sign":
        _write_csv(
            path=real_estate_paths["values_path"],
            columns=real_estate_core.VALUE_COLUMNS,
            rows=[["Donau87", "2026-01-01", -1, "WOZ", "Invalid value"]],
        )
        with pytest.raises(ValueError, match=expected_pattern):
            load_home_values(asof_date="2026-12-31")
        return

    raise AssertionError(f"Unknown validation case: {case_name}")


def test_mortgage_requires_origination_first(real_estate_paths) -> None:
    _write_csv(
        path=real_estate_paths["costs_path"],
        columns=real_estate_core.COST_COLUMNS,
        rows=[["Donau87", "2024-05-01", "INITIAL_PAYMENT", 25000, "Down payment"]],
    )
    _write_csv(
        path=real_estate_paths["inflows_path"],
        columns=real_estate_core.INFLOW_COLUMNS,
        rows=[["Donau87", "2026-01-01", "AVOIDED_RENT", 1400, "Saved rent"]],
    )
    _write_csv(
        path=real_estate_paths["values_path"],
        columns=real_estate_core.VALUE_COLUMNS,
        rows=[["Donau87", "2025-01-01", 561000, "WOZ", "WOZ 2025"]],
    )
    _write_csv(
        path=real_estate_paths["asset_folder"] / "mortgage_abn.csv",
        columns=real_estate_core.MORTGAGE_COLUMNS,
        rows=[
            ["Donau87", "DONAU87_M1", "2026-01-01", "PAYMENT", 0, 800, 1000, "Invalid first row"],
            ["Donau87", "DONAU87_M1", "2026-02-01", "PAYMENT", 0, 790, 1000, "Payment"],
        ],
    )

    with pytest.raises(ValueError, match="ORIGINATION"):
        load_mortgage_files()


def test_summarize_mortgages_calculates_outstanding(real_estate_paths) -> None:
    _seed_valid_files(
        asset_folder=real_estate_paths["asset_folder"],
        costs_path=real_estate_paths["costs_path"],
        inflows_path=real_estate_paths["inflows_path"],
        values_path=real_estate_paths["values_path"],
    )

    summary = summarize_mortgages()
    assert list(summary.columns) == [
        "Asset",
        "Mortgage ID",
        "Initial Principal",
        "Interest Paid",
        "Principal Repaid",
        "Outstanding Principal",
        "Cash Out",
    ]

    first = summary[summary["Mortgage ID"] == "DONAU87_M1"].iloc[0]
    second = summary[summary["Mortgage ID"] == "DONAU87_M2"].iloc[0]

    assert first["Outstanding Principal"] == 298000
    assert first["Cash Out"] == 3590
    assert second["Outstanding Principal"] == 99400
    assert second["Cash Out"] == 1099


def test_summarize_real_estate_net_cash_out(real_estate_paths) -> None:
    _seed_valid_files(
        asset_folder=real_estate_paths["asset_folder"],
        costs_path=real_estate_paths["costs_path"],
        inflows_path=real_estate_paths["inflows_path"],
        values_path=real_estate_paths["values_path"],
    )

    summary = summarize_real_estate(asof_date="2026-12-31")
    assert len(summary) == 1
    row = summary.iloc[0]

    assert row["Asset"] == "Donau87"
    assert row["Total Home Costs"] == 27200
    assert row["Total Mortgage Interest"] == 2089
    assert row["Total Mortgage Repayment"] == 2600
    assert row["Total Inflows"] == 2800
    assert row["Net Cash Out"] == 29089
    assert row["Total Outstanding Mortgage"] == 397400
    assert row["Current Property Value"] == 558000
    assert row["Estimated Equity"] == 160600


def test_asof_filters_future_rows(real_estate_paths) -> None:
    _seed_valid_files(
        asset_folder=real_estate_paths["asset_folder"],
        costs_path=real_estate_paths["costs_path"],
        inflows_path=real_estate_paths["inflows_path"],
        values_path=real_estate_paths["values_path"],
    )

    summary = summarize_real_estate(asof_date="2025-12-31")
    row = summary.iloc[0]

    assert row["Total Home Costs"] == 27200
    assert row["Total Mortgage Interest"] == 0
    assert row["Total Mortgage Repayment"] == 0
    assert row["Total Inflows"] == 0
    assert row["Net Cash Out"] == 27200
    assert row["Total Outstanding Mortgage"] == 400000
    assert row["Current Property Value"] == 561000
    assert row["Estimated Equity"] == 161000


def test_default_asof_date_is_today(real_estate_paths) -> None:
    _seed_valid_files(
        asset_folder=real_estate_paths["asset_folder"],
        costs_path=real_estate_paths["costs_path"],
        inflows_path=real_estate_paths["inflows_path"],
        values_path=real_estate_paths["values_path"],
    )
    existing_inflows = pd.read_csv(real_estate_paths["inflows_path"])
    future_inflow = pd.DataFrame(
        [["Donau87", "2099-01-01", "AVOIDED_RENT", 9999, "Future row"]],
        columns=real_estate_core.INFLOW_COLUMNS,
    )
    pd.concat([existing_inflows, future_inflow], ignore_index=True).to_csv(
        real_estate_paths["inflows_path"], index=False
    )

    summary_default = summarize_real_estate()
    summary_future = summarize_real_estate(asof_date="2099-12-31")

    assert summary_default.iloc[0]["Total Inflows"] == 2800
    assert summary_future.iloc[0]["Total Inflows"] == 12799


def test_ownership_shares_are_applied(real_estate_paths) -> None:
    _seed_valid_files(
        asset_folder=real_estate_paths["asset_folder"],
        costs_path=real_estate_paths["costs_path"],
        inflows_path=real_estate_paths["inflows_path"],
        values_path=real_estate_paths["values_path"],
    )
    _write_csv(
        path=real_estate_paths["ownership_path"],
        columns=real_estate_core.OWNERSHIP_COLUMNS,
        rows=[
            ["ASSET", "Donau87", 0.5, "Half ownership of the asset"],
            ["MORTGAGE", "DONAU87_M2", 1.0, "Full ownership for mortgage 2"],
        ],
    )

    mortgage_summary = summarize_mortgages(asof_date="2026-12-31")
    m1 = mortgage_summary[mortgage_summary["Mortgage ID"] == "DONAU87_M1"].iloc[0]
    m2 = mortgage_summary[mortgage_summary["Mortgage ID"] == "DONAU87_M2"].iloc[0]

    assert m1["Initial Principal"] == 150000
    assert m1["Interest Paid"] == 795
    assert m1["Principal Repaid"] == 1000
    assert m1["Outstanding Principal"] == 149000
    assert m2["Initial Principal"] == 100000
    assert m2["Interest Paid"] == 499
    assert m2["Principal Repaid"] == 600
    assert m2["Outstanding Principal"] == 99400

    summary = summarize_real_estate(asof_date="2026-12-31")
    row = summary.iloc[0]
    assert row["Total Home Costs"] == 13600
    assert row["Total Mortgage Interest"] == 1294
    assert row["Total Mortgage Repayment"] == 1600
    assert row["Total Inflows"] == 1400
    assert row["Net Cash Out"] == 15094
    assert row["Total Outstanding Mortgage"] == 248400
    assert row["Current Property Value"] == 279000
    assert row["Estimated Equity"] == 30600


@pytest.mark.parametrize(
    ("ownership_rows", "expected_pattern"),
    [
        ([["ASSET", "Donau87", 1.2, "Out of range"]], "must be in \\(0, 1\\]"),
        ([["INVALID", "Donau87", 0.5, "Invalid scope"]], "Use ASSET or MORTGAGE"),
        (
            [
                ["MORTGAGE", "DONAU87_M2", 0.5, "Primary"],
                ["MORTGAGE", "donau87_m2", 0.4, "Duplicate case-insensitive"],
            ],
            "Duplicate mortgage Identifier",
        ),
    ],
)
def test_invalid_ownership_config_raises(
    real_estate_paths, ownership_rows: list[list[object]], expected_pattern: str
) -> None:
    _write_csv(
        path=real_estate_paths["ownership_path"],
        columns=real_estate_core.OWNERSHIP_COLUMNS,
        rows=ownership_rows,
    )

    with pytest.raises(ValueError, match=expected_pattern):
        load_home_costs(asof_date="2026-12-31")


def test_mortgage_specific_ownership_override_applies(real_estate_paths) -> None:
    _seed_valid_files(
        asset_folder=real_estate_paths["asset_folder"],
        costs_path=real_estate_paths["costs_path"],
        inflows_path=real_estate_paths["inflows_path"],
        values_path=real_estate_paths["values_path"],
    )
    _write_csv(
        path=real_estate_paths["ownership_path"],
        columns=real_estate_core.OWNERSHIP_COLUMNS,
        rows=[["MORTGAGE", "donau87_m2", 0.5, "Half ownership for mortgage 2"]],
    )

    mortgage_summary = summarize_mortgages(asof_date="2026-12-31")
    m1 = mortgage_summary[mortgage_summary["Mortgage ID"] == "DONAU87_M1"].iloc[0]
    m2 = mortgage_summary[mortgage_summary["Mortgage ID"] == "DONAU87_M2"].iloc[0]

    assert m1["Initial Principal"] == 300000
    assert m1["Interest Paid"] == 1590
    assert m1["Principal Repaid"] == 2000
    assert m1["Outstanding Principal"] == 298000

    assert m2["Initial Principal"] == 50000
    assert m2["Interest Paid"] == pytest.approx(249.5)
    assert m2["Principal Repaid"] == 300
    assert m2["Outstanding Principal"] == 49700


def test_real_estate_core_empty_outputs_are_canonical(real_estate_paths) -> None:
    costs = load_home_costs(asof_date="2026-12-31")
    inflows = load_home_inflows(asof_date="2026-12-31")
    values = load_home_values(asof_date="2026-12-31")
    mortgages = load_mortgage_files(asof_date="2026-12-31")
    mortgage_summary = summarize_mortgages(asof_date="2026-12-31")
    summary = summarize_real_estate(asof_date="2026-12-31")

    assert costs.empty
    assert inflows.empty
    assert values.empty
    assert mortgages.empty
    assert mortgage_summary.empty
    assert summary.empty

    assert list(costs.columns) == real_estate_core.COST_COLUMNS
    assert list(inflows.columns) == real_estate_core.INFLOW_COLUMNS
    assert list(values.columns) == real_estate_core.VALUE_COLUMNS
    assert list(mortgages.columns) == real_estate_core.MORTGAGE_COLUMNS
    assert list(mortgage_summary.columns) == [
        "Asset",
        "Mortgage ID",
        "Initial Principal",
        "Interest Paid",
        "Principal Repaid",
        "Outstanding Principal",
        "Cash Out",
    ]
    assert list(summary.columns) == [
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
