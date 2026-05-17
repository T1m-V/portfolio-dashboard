from __future__ import annotations

from pathlib import Path

APP_SOURCE = (
    Path(__file__).resolve().parents[1] / "src" / "dashboard" / "frontend" / "src" / "App.tsx"
)


def _between(source: str, start: str, end: str) -> str:
    start_index = source.index(start)
    end_index = source.index(end, start_index)
    return source[start_index:end_index]


def test_arbitrum_dashboard_uses_shared_as_of_date_selector() -> None:
    source = APP_SOURCE.read_text()
    arbitrum_dashboard = _between(
        source,
        "function ArbitrumDashboard",
        "function InvestmentDashboard",
    )
    app_render = _between(source, 'active === "arbitrum"', 'active === "realEstate"')

    assert "onAsOfDateChange" in arbitrum_dashboard
    assert (
        '<DateField label="To date" value={date} onChange={onAsOfDateChange} />'
        in arbitrum_dashboard
    )
    assert "onAsOfDateChange={handleAsOfDateChange}" in app_render


def test_arbitrum_dashboard_uses_shared_period_selector() -> None:
    source = APP_SOURCE.read_text()
    arbitrum_dashboard = _between(
        source,
        "function ArbitrumDashboard",
        "function InvestmentDashboard",
    )
    app_render = _between(source, 'active === "arbitrum"', 'active === "realEstate"')

    assert "fromDate" in arbitrum_dashboard
    assert "period: PeriodKey" in arbitrum_dashboard
    assert "onFromDateChange" in arbitrum_dashboard
    assert "onPeriodChange" in arbitrum_dashboard
    assert "<PeriodSelector value={period} onChange={onPeriodChange} />" in arbitrum_dashboard
    assert (
        '<DateField label="From" value={fromDate} max={date} onChange={onFromDateChange} />'
        in arbitrum_dashboard
    )
    assert "fromDate={fromDate}" in app_render
    assert "period={period}" in app_render
    assert "onFromDateChange={handleFromDateChange}" in app_render
    assert "onPeriodChange={handlePeriodChange}" in app_render
