from __future__ import annotations

import pandas as pd
from fastapi.testclient import TestClient

import dashboard.main as main
import dashboard.services as services
from dashboard.data_handling.real_estate_data import RealEstateDataBundle


def test_stock_payload_preserves_investment_metrics(monkeypatch) -> None:
    frame = pd.DataFrame(
        [
            {
                "Date": pd.Timestamp("2026-01-01"),
                "ISIN": "AAA",
                "Quantity": 2.0,
                "Price": 50.0,
                "Market Value": 100.0,
                "Principal Invested": 80.0,
                "Cumulative Fees": 2.0,
                "Cumulative Taxes": 1.0,
                "Gross Dividends": 3.0,
                "Asset Name": "Alpha",
                "group": "ETF",
            }
        ]
    )
    monkeypatch.setattr(
        services,
        "load_and_process_data_group_stocks",
        lambda **_: frame,
    )
    monkeypatch.setattr(
        services,
        "load_recent_stock_transactions",
        lambda **_: pd.DataFrame([{"Date": "2026-01-01", "Type": "Buy", "Asset Name": "Alpha"}]),
    )

    payload = services.build_stock_payload(
        selected_date="2026-01-01",
        from_date="2026-01-01",
        mode="full",
        selection="",
        composition="name",
    )

    metrics = {item["label"]: item["value"] for item in payload["summary"]["metrics"]}
    assert metrics["Current Value"] == 100.0
    assert metrics["Net Invested"] == 80.0
    assert metrics["Net P/L"] == 20.0
    assert payload["composition"]["kind"] == "breakdown"
    assert payload["transactions"]["rows"][0]["Type"] == "Buy"


def test_nexo_payload_formats_recent_transaction_columns(monkeypatch) -> None:
    frame = pd.DataFrame(
        [
            {
                "Date": pd.Timestamp("2026-01-01"),
                "Coin": "BTC",
                "Quantity": 1.0,
                "Price": 10.0,
                "Market Value": 10.0,
                "Principal Invested": 7.0,
                "Cumulative Fees": 0.0,
                "Cumulative Taxes": 0.0,
                "Gross Dividends": 0.0,
                "Asset Name": "Bitcoin",
                "Asset Group": "Crypto",
                "Currency": "USD",
            }
        ]
    )
    tx = pd.DataFrame(
        [
            {
                "Date": "2026-01-01 10:00",
                "Type": "Exchange",
                "Input Amount": "-1",
                "Input Currency": "USDT",
                "Output Amount": "0.1",
                "Output Currency": "BTC",
                "USD Equivalent": "100",
                "Details": "trade",
            }
        ]
    )
    monkeypatch.setattr(services, "load_and_process_nexo_data", lambda **_: frame)
    monkeypatch.setattr(services, "load_recent_nexo_transactions", lambda **_: tx)

    payload = services.build_nexo_payload(
        selected_date="2026-01-01",
        from_date="2026-01-01",
        mode="full",
        selection="",
        composition="group",
    )

    assert payload["summary"]["profitLoss"] == 3.0
    assert payload["transactions"]["rows"][0]["Input"] == "-1 USDT"
    assert payload["transactions"]["rows"][0]["Output"] == "0.1 BTC"


def test_real_estate_payload_handles_empty_frames_and_warnings(monkeypatch) -> None:
    empty = pd.DataFrame()
    bundle = RealEstateDataBundle(
        costs=empty,
        inflows=empty,
        values=empty,
        mortgages=empty,
        errors=["home costs: missing"],
    )
    monkeypatch.setattr(services, "load_real_estate_bundle", lambda **_: bundle)

    payload = services.build_real_estate_payload(
        selected_date="2026-01-01",
        from_date="2026-01-01",
        asset="ALL",
        outflow_limit=5,
        inflow_limit=5,
    )

    assert payload["warnings"] == ["home costs: missing"]
    assert payload["summary"]["metrics"][0]["value"] == 0.0
    assert payload["recentOutflows"]["rows"] == []
    assert payload["recentInflows"]["rows"] == []


def test_real_estate_api_endpoint_uses_query_contract(monkeypatch) -> None:
    def fake_payload(**kwargs):
        assert kwargs == {
            "selected_date": "2026-01-01",
            "from_date": "2025-01-01",
            "asset": "ALL",
            "outflow_limit": "10",
            "inflow_limit": "25",
        }
        return {"warnings": ["ok"]}

    monkeypatch.setattr(main, "build_real_estate_payload", fake_payload)

    client = TestClient(main.app)
    response = client.get(
        "/api/real-estate?date=2026-01-01&fromDate=2025-01-01&asset=ALL&outflowLimit=10&inflowLimit=25"
    )

    assert response.status_code == 200
    assert response.json() == {"warnings": ["ok"]}


def test_investment_api_endpoints_pass_from_date(monkeypatch) -> None:
    def fake_stock_payload(**kwargs):
        assert kwargs["selected_date"] == "2026-01-31"
        assert kwargs["from_date"] == "2026-01-01"
        return {"kind": "stocks"}

    def fake_nexo_payload(**kwargs):
        assert kwargs["selected_date"] == "2026-01-31"
        assert kwargs["from_date"] == "2026-01-01"
        return {"kind": "nexo"}

    monkeypatch.setattr(main, "build_stock_payload", fake_stock_payload)
    monkeypatch.setattr(main, "build_nexo_payload", fake_nexo_payload)

    client = TestClient(main.app)

    stock_response = client.get("/api/stocks?date=2026-01-31&fromDate=2026-01-01")
    nexo_response = client.get("/api/nexo?date=2026-01-31&fromDate=2026-01-01")

    assert stock_response.status_code == 200
    assert stock_response.json() == {"kind": "stocks"}
    assert nexo_response.status_code == 200
    assert nexo_response.json() == {"kind": "nexo"}


def test_stock_period_profit_loss_uses_from_date_baseline(monkeypatch) -> None:
    frame = pd.DataFrame(
        [
            {
                "Date": pd.Timestamp("2026-01-01"),
                "ISIN": "AAA",
                "Quantity": 1.0,
                "Price": 100.0,
                "Market Value": 100.0,
                "Principal Invested": 100.0,
                "Cumulative Fees": 0.0,
                "Cumulative Taxes": 0.0,
                "Gross Dividends": 0.0,
                "Asset Name": "Alpha",
            },
            {
                "Date": pd.Timestamp("2026-01-02"),
                "ISIN": "AAA",
                "Quantity": 1.5,
                "Price": 106.67,
                "Market Value": 160.0,
                "Principal Invested": 150.0,
                "Cumulative Fees": 2.0,
                "Cumulative Taxes": 1.0,
                "Gross Dividends": 0.0,
                "Asset Name": "Alpha",
            },
            {
                "Date": pd.Timestamp("2026-01-03"),
                "ISIN": "AAA",
                "Quantity": 1.8,
                "Price": 116.67,
                "Market Value": 210.0,
                "Principal Invested": 180.0,
                "Cumulative Fees": 3.0,
                "Cumulative Taxes": 1.0,
                "Gross Dividends": 5.0,
                "Asset Name": "Alpha",
            },
        ]
    )
    monkeypatch.setattr(services, "load_and_process_data_group_stocks", lambda **_: frame)
    monkeypatch.setattr(services, "load_recent_stock_transactions", lambda **_: pd.DataFrame())
    monkeypatch.setattr(services, "get_stock_start_date", lambda **_: "2026-01-01")

    payload = services.build_stock_payload(
        selected_date="2026-01-03",
        from_date="2026-01-02",
        mode="full",
        selection="",
        composition="name",
    )

    metrics = {item["label"]: item["value"] for item in payload["summary"]["metrics"]}
    assert metrics["Current Value"] == 210.0
    assert metrics["Net Invested"] == 79.0
    assert metrics["Net P/L"] == 31.0
    assert metrics["Dividends"] == 5.0
    assert [row["Date"] for row in payload["history"]] == ["2026-01-02", "2026-01-03"]
    assert payload["history"][0]["Invested Capital"] == 153.0
    assert payload["history"][-1]["Invested Capital"] == 179.0
    assert payload["history"][-1]["Profit/Loss"] == 31.0


def test_nexo_period_profit_loss_uses_from_date_baseline(monkeypatch) -> None:
    frame = pd.DataFrame(
        [
            {
                "Date": pd.Timestamp("2026-01-01"),
                "Coin": "BTC",
                "Quantity": 1.0,
                "Price": 100.0,
                "Market Value": 100.0,
                "Principal Invested": 100.0,
                "Cumulative Fees": 0.0,
                "Cumulative Taxes": 0.0,
                "Gross Dividends": 0.0,
                "Asset Name": "Bitcoin",
                "Asset Group": "Crypto",
                "Currency": "USD",
            },
            {
                "Date": pd.Timestamp("2026-01-02"),
                "Coin": "BTC",
                "Quantity": 1.2,
                "Price": 125.0,
                "Market Value": 150.0,
                "Principal Invested": 130.0,
                "Cumulative Fees": 0.0,
                "Cumulative Taxes": 0.0,
                "Gross Dividends": 0.0,
                "Asset Name": "Bitcoin",
                "Asset Group": "Crypto",
                "Currency": "USD",
            },
        ]
    )
    monkeypatch.setattr(services, "load_and_process_nexo_data", lambda **_: frame)
    monkeypatch.setattr(services, "load_recent_nexo_transactions", lambda **_: pd.DataFrame())
    monkeypatch.setattr(services, "get_nexo_start_date", lambda **_: "2026-01-01")

    payload = services.build_nexo_payload(
        selected_date="2026-01-02",
        from_date="2026-01-02",
        mode="full",
        selection="",
        composition="group",
    )

    metrics = {item["label"]: item["value"] for item in payload["summary"]["metrics"]}
    assert metrics["Net Invested"] == 30.0
    assert metrics["Net P/L"] == 20.0


def test_real_estate_period_metrics_and_rebased_pl(monkeypatch) -> None:
    costs = pd.DataFrame(
        [
            ["Donau87", "2025-01-01", "INITIAL_PAYMENT", 1000.0, ""],
            ["Donau87", "2025-02-01", "MAINTENANCE", 100.0, ""],
        ],
        columns=["Asset", "Date", "Cost Type", "Amount", "Notes"],
    )
    inflows = pd.DataFrame(
        [["Donau87", "2025-02-15", "AVOIDED_RENT", 50.0, ""]],
        columns=["Asset", "Date", "Inflow Type", "Amount", "Notes"],
    )
    values = pd.DataFrame(
        [
            ["Donau87", "2025-01-01", 5000.0, "WOZ", ""],
            ["Donau87", "2025-03-01", 5200.0, "WOZ", ""],
        ],
        columns=["Asset", "Date", "Value", "Valuation Type", "Notes"],
    )
    mortgages = pd.DataFrame(
        [
            ["Donau87", "M1", "2025-01-01", "ORIGINATION", 3000.0, 0.0, 0.0, ""],
            ["Donau87", "M1", "2025-02-01", "PAYMENT", 0.0, 20.0, 100.0, ""],
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

    bundle = RealEstateDataBundle(
        costs=costs,
        inflows=inflows,
        values=values,
        mortgages=mortgages,
        errors=[],
    )
    monkeypatch.setattr(services, "load_real_estate_bundle", lambda **_: bundle)

    payload = services.build_real_estate_payload(
        selected_date="2025-03-15",
        from_date="2025-02-01",
        asset="ALL",
        outflow_limit=5,
        inflow_limit=5,
    )

    metrics = {item["label"]: item["value"] for item in payload["summary"]["metrics"]}
    assert metrics["Property Value"] == 5200.0
    assert metrics["Outstanding Mortgage"] == 2900.0
    assert metrics["Estimated Equity"] == 2300.0
    assert metrics["Net Cash Out"] == 170.0
    assert payload["cashflow"][0]["Cumulative Net Cash Flow"] == -170.0
    assert payload["plBreakdown"][0]["Date"] == "2025-02-01"
    assert payload["plBreakdown"][0]["Total P/L"] == 0.0
    assert payload["outflowBreakdown"]
    assert payload["inflowBreakdown"] == [{"label": "AVOIDED_RENT", "value": 50.0}]
