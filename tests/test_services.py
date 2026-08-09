from types import SimpleNamespace

import pandas as pd

import portfolio_dashboard.services as services
from portfolio_dashboard.arbitrum import ArbitrumArtifacts

INVESTMENT_COLUMNS = [
    "Date",
    "ISIN",
    "Quantity",
    "Market Value",
    "Principal Invested",
    "Cumulative Fees",
    "Cumulative Taxes",
    "Gross Dividends",
    "Asset Name",
]


def test_options_payload_contains_only_data_driven_assets(monkeypatch) -> None:
    context = SimpleNamespace(
        stock_metadata=lambda: {
            "AAA": {
                "name": "Alpha",
                "group": "Stocks",
                "region": "EUROPE",
                "provider": "Direct",
            }
        },
        currency_metadata=lambda: {"BTC": {"name": "Bitcoin"}},
    )
    monkeypatch.setattr(services, "active_context", lambda: context)
    monkeypatch.setattr(services, "list_nexo_coins", lambda: ["BTC"])
    monkeypatch.setattr(
        services,
        "load_arbitrum_assets",
        lambda _chain: pd.DataFrame([["Ether", "ETH"]], columns=["Label", "Value"]),
    )
    assert services.build_options_payload() == {
        "stocks": [
            {
                "label": "Alpha",
                "value": "AAA",
                "group": "Stocks",
                "region": "EUROPE",
                "provider": "Direct",
            }
        ],
        "nexo": [{"label": "Bitcoin", "value": "BTC"}],
        "arbitrum": [{"label": "Ether", "value": "ETH"}],
    }


def test_stock_payload_rebases_the_period_and_requests_only_securities(monkeypatch) -> None:
    metadata = {
        "AAA": {
            "name": "Alpha",
            "ticker": "A",
            "group": "Stocks",
            "region": "EUROPE",
            "provider": "Direct",
        }
    }
    context = SimpleNamespace(stock_metadata=lambda: metadata)
    requested: list[list[str]] = []
    frame = pd.DataFrame(
        [
            ["2024-12-31", "AAA", 1.0, 100.0, 100.0, 0.0, 0.0, 0.0, "Alpha"],
            ["2025-01-31", "AAA", 1.0, 120.0, 110.0, 0.0, 0.0, 0.0, "Alpha"],
        ],
        columns=INVESTMENT_COLUMNS,
    )
    frame["Date"] = pd.to_datetime(frame["Date"])

    def load_history(*, context, end_date, isins):
        requested.append(isins)
        return frame

    monkeypatch.setattr(services, "active_context", lambda: context)
    monkeypatch.setattr(services, "load_stock_history", load_history)
    monkeypatch.setattr(services, "get_stock_start_date", lambda **_kwargs: "2024-12-31")
    monkeypatch.setattr(
        services,
        "load_recent_stock_transactions",
        lambda **_kwargs: pd.DataFrame(columns=["Date", "Type"]),
    )

    payload = services.build_stock_payload(
        selected_date="2025-01-31",
        from_date="2025-01-01",
        dimension="group",
        selection="ALL",
        composition="name",
    )

    assert requested == [["AAA"]]
    assert {metric["label"]: metric["value"] for metric in payload["metrics"]} == {
        "Current Value": 120.0,
        "Net P/L": 10.0,
        "Net Invested": 10.0,
        "Dividends": 0.0,
        "Fees": 0.0,
        "Taxes": 0.0,
    }
    assert payload["history"] == [
        {
            "Date": "2025-01-31",
            "Market Value": 120.0,
            "Invested Capital": 110.0,
            "Quantity": 1.0,
            "Profit/Loss": 10.0,
        }
    ]
    assert payload["composition"]["items"] == [{"label": "Alpha", "value": 120.0}]


def test_nexo_payload_has_only_all_or_coin_selection(monkeypatch) -> None:
    context = SimpleNamespace(
        currency_metadata=lambda: {
            "BTC": {"name": "Bitcoin", "ticker": "BTC", "group": "Crypto", "currency": "USD"}
        }
    )
    frame = pd.DataFrame(
        [["2025-01-31", "BTC", 1.0, 100.0, 90.0, 0.0, 0.0, 0.0, "Bitcoin"]],
        columns=INVESTMENT_COLUMNS,
    )
    frame["Date"] = pd.to_datetime(frame["Date"])
    transaction = pd.DataFrame(
        [[pd.Timestamp("2025-01-20"), "Exchange", 1, "EUR", 1.1, "USD", 1.1, ""]],
        columns=[
            "Date",
            "Type",
            "Input Amount",
            "Input Currency",
            "Output Amount",
            "Output Currency",
            "USD Equivalent",
            "Details",
        ],
    )
    calls: list[list[str] | None] = []
    monkeypatch.setattr(services, "active_context", lambda: context)
    monkeypatch.setattr(
        services,
        "load_and_process_nexo_data",
        lambda end_date_str, coins: calls.append(coins) or frame,
    )
    monkeypatch.setattr(services, "load_recent_nexo_transactions", lambda **_kwargs: transaction)
    monkeypatch.setattr(services, "get_nexo_start_date", lambda **_kwargs: "2025-01-01")

    payload = services.build_nexo_payload(
        selected_date="2025-01-31", from_date="2025-01-01", coin="BTC"
    )
    assert calls == [["BTC"]]
    assert payload["title"] == "Bitcoin"
    assert payload["composition"]["kind"] == "metadata"
    assert payload["transactions"]["rows"][0]["Input"] == "1 EUR"


def test_arbitrum_payload_filters_asset_period_sources_and_transactions(monkeypatch) -> None:
    timeseries = pd.DataFrame(
        [
            ["2025-01-01", "ALL", 100, 80, 20, 0, 2],
            ["2025-01-01", "BTC", 40, 30, 10, 0.01, 1],
            ["2025-02-01", "BTC", 50, 35, 15, 0.01, 2],
        ],
        columns=[
            "Date",
            "Selection",
            "MarketValueEUR",
            "PrincipalInvestedEUR",
            "ProfitLossEUR",
            "Quantity",
            "TxCount",
        ],
    )
    composition = pd.DataFrame(
        [["2025-02-01", "BTC", "name", "BTC", 50]],
        columns=["Date", "Selection", "CompositionMode", "Label", "ValueEUR"],
    )
    sources = pd.DataFrame(
        [["2025-02-01", "BTC", "Aave", "BTC", 0.01, 50, 35, 15, "AAVE"]],
        columns=[
            "Date",
            "Selection",
            "Source",
            "Coin",
            "Quantity",
            "MarketValueEUR",
            "PrincipalInvestedEUR",
            "ProfitLossEUR",
            "ValuationRoute",
        ],
    )
    transactions = pd.DataFrame(
        [["2025-01-15", "Receive", "BTC", 0.01, "", 0, 0, "ETH", "hash", "BTC"]],
        columns=[
            "Date",
            "Type",
            "Token in",
            "Qty in",
            "Token out",
            "Qty out",
            "Fee",
            "Fee Token",
            "TX Hash",
            "AssetKeys",
        ],
    )
    for frame in (timeseries, composition, sources, transactions):
        frame["Date"] = pd.to_datetime(frame["Date"])
    artifacts = ArbitrumArtifacts(
        timeseries=timeseries,
        composition=composition,
        sources=sources,
        transactions=transactions,
        warnings=[],
    )
    monkeypatch.setattr(services, "load_arbitrum_artifacts", lambda _chain: artifacts)

    payload = services.build_arbitrum_payload(
        selected_date="2025-02-01",
        from_date="2025-01-15",
        asset="BTC",
        composition="name",
        currency_unit="EUR",
    )
    assert payload["history"] == [
        {
            "Date": "2025-02-01",
            "Market Value": 50,
            "Invested Capital": 35,
            "Profit/Loss": 15,
            "Quantity": 0.01,
        }
    ]
    assert payload["metrics"][0]["value"] == 50
    assert payload["sources"]["rows"][0]["Source"] == "Aave"
    assert payload["transactions"]["rows"][0]["TX Hash"] == "hash"


def test_missing_investment_data_is_an_empty_state(monkeypatch) -> None:
    context = SimpleNamespace(stock_metadata=lambda: {})
    monkeypatch.setattr(services, "active_context", lambda: context)
    monkeypatch.setattr(services, "load_stock_history", lambda **_kwargs: pd.DataFrame())
    monkeypatch.setattr(
        services, "load_recent_stock_transactions", lambda **_kwargs: pd.DataFrame()
    )
    monkeypatch.setattr(services, "get_stock_start_date", lambda **_kwargs: None)
    payload = services.build_stock_payload(
        selected_date="2025-01-31",
        from_date="2025-01-01",
        dimension="group",
        selection="ALL",
        composition="name",
    )
    assert payload["metrics"] == []
    assert payload["history"] == []
    assert payload["composition"] == {"kind": "empty", "items": []}
