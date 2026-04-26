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
            "asset": "ALL",
            "outflow_limit": "10",
            "inflow_limit": "25",
        }
        return {"warnings": ["ok"]}

    monkeypatch.setattr(main, "build_real_estate_payload", fake_payload)

    client = TestClient(main.app)
    response = client.get(
        "/api/real-estate?date=2026-01-01&asset=ALL&outflowLimit=10&inflowLimit=25"
    )

    assert response.status_code == 200
    assert response.json() == {"warnings": ["ok"]}
