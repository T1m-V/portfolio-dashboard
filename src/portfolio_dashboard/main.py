from __future__ import annotations

import os
import signal
import threading
from datetime import date
from pathlib import Path
from typing import Literal

from fastapi import BackgroundTasks, FastAPI, HTTPException, Query, Request, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from portfolio_core import PortfolioSettings

from portfolio_dashboard.refresh_jobs import (
    RefreshAlreadyRunningError,
    RefreshKind,
    refresh_jobs,
)
from portfolio_dashboard.services import (
    build_arbitrum_payload,
    build_nexo_payload,
    build_options_payload,
    build_real_estate_payload,
    build_stock_payload,
)

app = FastAPI(title="Portfolio Dashboard")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173", "http://127.0.0.1:5173"],
    allow_origin_regex=r"http://(localhost|127\.0\.0\.1):\d+",
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/api/options")
def options() -> dict:
    return build_options_payload()


def request_server_stop() -> None:
    threading.Timer(0.25, lambda: os.kill(os.getpid(), signal.SIGTERM)).start()


def require_local_request(request: Request) -> None:
    client_host = request.client.host if request.client else None
    if client_host not in {"127.0.0.1", "::1", "testclient"}:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Local access only")


@app.post("/api/server/stop")
def stop_server(request: Request, background_tasks: BackgroundTasks) -> dict:
    require_local_request(request)
    background_tasks.add_task(request_server_stop)
    return {"status": "stopping"}


@app.post("/api/refresh/{kind}", status_code=status.HTTP_202_ACCEPTED)
def start_refresh(kind: RefreshKind, request: Request) -> dict[str, object]:
    require_local_request(request)
    try:
        return refresh_jobs.start(kind=kind, data_dir=PortfolioSettings.load().data_dir)
    except RefreshAlreadyRunningError as exc:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc)) from exc


@app.get("/api/refresh/jobs")
def list_refresh_jobs(request: Request) -> list[dict[str, object]]:
    require_local_request(request)
    return refresh_jobs.list()


@app.get("/api/refresh/jobs/{job_id}")
def get_refresh_job(job_id: str, request: Request) -> dict[str, object]:
    require_local_request(request)
    job = refresh_jobs.get(job_id)
    if job is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Refresh job not found")
    return job


@app.get("/api/stocks")
def stocks(
    date_: date = Query(alias="date"),
    from_date: date | None = Query(default=None, alias="fromDate"),
    mode: Literal["full", "group", "region", "provider", "name"] = "full",
    selection: str = "",
    composition: Literal["name", "group", "region", "provider"] = "name",
) -> dict:
    return build_stock_payload(
        selected_date=date_.isoformat(),
        from_date=from_date.isoformat() if from_date else None,
        mode=mode,
        selection=selection,
        composition=composition,
    )


@app.get("/api/nexo")
def nexo(
    date_: date = Query(alias="date"),
    from_date: date | None = Query(default=None, alias="fromDate"),
    mode: Literal["full", "group", "currency", "name"] = "full",
    selection: str = "",
    composition: Literal["name", "group", "currency"] = "name",
) -> dict:
    return build_nexo_payload(
        selected_date=date_.isoformat(),
        from_date=from_date.isoformat() if from_date else None,
        mode=mode,
        selection=selection,
        composition=composition,
    )


@app.get("/api/arbitrum")
def arbitrum(
    date_: date = Query(alias="date"),
    from_date: date | None = Query(default=None, alias="fromDate"),
    mode: Literal["full", "name"] = "full",
    selection: str = "",
    composition: Literal["name", "route", "exposure"] = "name",
    currency: Literal["EUR", "USD"] = "EUR",
) -> dict:
    return build_arbitrum_payload(
        selected_date=date_.isoformat(),
        from_date=from_date.isoformat() if from_date else None,
        mode=mode,
        selection=selection,
        composition=composition,
        currency=currency,
    )


@app.get("/api/real-estate")
def real_estate(
    date_: date = Query(alias="date"),
    from_date: date | None = Query(default=None, alias="fromDate"),
    asset: str = "ALL",
    outflowLimit: int | str = 5,
    inflowLimit: int | str = 5,
) -> dict:
    return build_real_estate_payload(
        selected_date=date_.isoformat(),
        from_date=from_date.isoformat() if from_date else None,
        asset=asset,
        outflow_limit=outflowLimit,
        inflow_limit=inflowLimit,
    )


static_root = Path(__file__).with_name("static")
if static_root.exists():
    app.mount("/", StaticFiles(directory=static_root, html=True), name="frontend")
