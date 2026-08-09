import pytest
from fastapi import HTTPException, Request
from fastapi.testclient import TestClient
from portfolio_core import active_context

import portfolio_dashboard.main as main


@pytest.mark.parametrize(
    ("path", "builder", "expected"),
    [
        (
            "/api/stocks?date=2026-02-03&fromDate=2026-01-01&dimension=region"
            "&selection=EUROPE&composition=provider",
            "build_stock_payload",
            {
                "selected_date": "2026-02-03",
                "from_date": "2026-01-01",
                "dimension": "region",
                "selection": "EUROPE",
                "composition": "provider",
            },
        ),
        (
            "/api/nexo?date=2026-02-03&fromDate=2026-01-01&coin=BTC",
            "build_nexo_payload",
            {"selected_date": "2026-02-03", "from_date": "2026-01-01", "coin": "BTC"},
        ),
        (
            "/api/arbitrum?date=2026-02-03&fromDate=2026-01-01&asset=ETH"
            "&composition=route&currency=USD",
            "build_arbitrum_payload",
            {
                "selected_date": "2026-02-03",
                "from_date": "2026-01-01",
                "asset": "ETH",
                "composition": "route",
                "currency_unit": "USD",
            },
        ),
        (
            "/api/real-estate?date=2026-02-03&fromDate=2026-01-01",
            "build_real_estate_payload",
            {"selected_date": "2026-02-03", "from_date": "2026-01-01"},
        ),
    ],
)
def test_dashboard_routes_use_the_small_query_contract(
    monkeypatch, path: str, builder: str, expected: dict
) -> None:
    monkeypatch.setattr(main, builder, lambda **kwargs: kwargs)
    response = TestClient(main.create_app(context=active_context())).get(path)
    assert response.status_code == 200
    assert response.json() == expected


def test_app_serves_the_bundle_and_rejects_remote_mutations() -> None:
    client = TestClient(main.create_app(context=active_context()))
    assert client.get("/").status_code == 200

    request = Request({"type": "http", "client": ("203.0.113.1", 5000)})
    with pytest.raises(HTTPException, match="Local access only"):
        main.require_local_request(request)


def test_refresh_api_exposes_one_job(monkeypatch) -> None:
    job = {"id": "job-1", "kind": "prices", "status": "queued", "logs": []}

    class Jobs:
        def start(self, **_kwargs):
            return job

        def get(self, job_id: str):
            return job if job_id == "job-1" else None

    monkeypatch.setattr(main, "request_server_stop", lambda: None)
    client = TestClient(main.create_app(context=active_context(), jobs=Jobs()))
    assert client.post("/api/refresh/prices").json() == job
    assert client.get("/api/refresh/jobs/job-1").json() == job
    assert client.get("/api/refresh/jobs/missing").status_code == 404
    assert client.post("/api/server/stop").json() == {"status": "stopping"}


def test_fastapi_rejects_invalid_dates_before_service_calls() -> None:
    response = TestClient(main.create_app(context=active_context())).get(
        "/api/stocks?date=not-a-date&fromDate=2026-01-01"
    )
    assert response.status_code == 422
