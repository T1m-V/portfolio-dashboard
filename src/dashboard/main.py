from __future__ import annotations

from datetime import date
from typing import Literal

from fastapi import FastAPI, Query
from fastapi.middleware.cors import CORSMiddleware

from dashboard.services import (
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
