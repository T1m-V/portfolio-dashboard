from __future__ import annotations

import datetime

import dash_bootstrap_components as dbc
import pandas as pd
from dash import Dash, dcc, html

from dashboard.callbacks.arbitrum_trial_dashboard import register_arbitrum_trial_dashboard_callbacks
from dashboard.data_handling.arbitrum_health_data import load_arbitrum_health_bundle
from dashboard.runtime import run_dash_app


def _resolve_default_snapshot_date() -> datetime.date:
    bundle = load_arbitrum_health_bundle()
    if bundle.snapshots.empty or "Date" not in bundle.snapshots.columns:
        return datetime.date.today()

    parsed = pd.to_datetime(bundle.snapshots["Date"], errors="coerce").dropna()
    if parsed.empty:
        return datetime.date.today()
    return pd.Timestamp(parsed.max()).date()


DEFAULT_DATE = _resolve_default_snapshot_date()

app = Dash(__name__, external_stylesheets=[dbc.themes.CERULEAN])

app.layout = dbc.Container(
    fluid=True,
    children=[
        dbc.Row(
            dbc.Col(
                html.H1(
                    "Arbitrum Trial Health Dashboard",
                    className="text-center my-4 text-primary",
                )
            )
        ),
        html.Div(id="arb-status"),
        dbc.Row(
            [
                dbc.Col(
                    [
                        html.Label("Reference Date:", className="fw-bold"),
                        dcc.DatePickerSingle(
                            id="arb-date-picker",
                            date=DEFAULT_DATE,
                            max_date_allowed=DEFAULT_DATE,
                            className="d-block",
                        ),
                    ],
                    xs=12,
                    md=4,
                    className="mb-3",
                ),
                dbc.Col(
                    [
                        html.Label("Asset:", className="fw-bold"),
                        dcc.Dropdown(
                            id="arb-asset-selector",
                            options=[{"label": "All Assets", "value": "ALL"}],
                            value="ALL",
                            clearable=False,
                        ),
                    ],
                    xs=12,
                    md=4,
                    className="mb-3",
                ),
                dbc.Col(
                    [
                        html.Label("Trend Window:", className="fw-bold"),
                        dcc.Dropdown(
                            id="arb-window",
                            options=[
                                {"label": "30D", "value": "30D"},
                                {"label": "90D", "value": "90D"},
                                {"label": "180D", "value": "180D"},
                                {"label": "ALL", "value": "ALL"},
                            ],
                            value="90D",
                            clearable=False,
                        ),
                    ],
                    xs=12,
                    md=4,
                    className="mb-3",
                ),
            ],
            className="bg-light p-3 rounded shadow-sm mb-3 align-items-end",
        ),
        html.Div(id="arb-kpi-cards", className="mb-2"),
        dbc.Row(
            [
                dbc.Col(
                    dbc.Card(
                        [
                            dbc.CardHeader("Dataset Freshness", className="fw-bold"),
                            dbc.CardBody(
                                dcc.Graph(id="arb-freshness-fig", config={"displayModeBar": False})
                            ),
                        ],
                        className="shadow-sm h-100",
                    ),
                    xs=12,
                    lg=6,
                    className="mb-4",
                ),
                dbc.Col(
                    dbc.Card(
                        [
                            dbc.CardHeader("Transaction Activity", className="fw-bold"),
                            dbc.CardBody(
                                dcc.Graph(id="arb-tx-fig", config={"displayModeBar": False})
                            ),
                        ],
                        className="shadow-sm h-100",
                    ),
                    xs=12,
                    lg=6,
                    className="mb-4",
                ),
            ]
        ),
        dbc.Row(
            dbc.Col(
                dbc.Card(
                    [
                        dbc.CardHeader("Valuation Route Mix", className="fw-bold"),
                        dbc.CardBody(
                            dcc.Graph(id="arb-route-mix-fig", config={"displayModeBar": False})
                        ),
                    ],
                    className="shadow-sm",
                ),
                xs=12,
                className="mb-4",
            )
        ),
        dbc.Row(
            [
                dbc.Col(
                    dbc.Card(
                        [
                            dbc.CardHeader("Exceptions Over Time", className="fw-bold"),
                            dbc.CardBody(
                                dcc.Graph(id="arb-exceptions-fig", config={"displayModeBar": False})
                            ),
                        ],
                        className="shadow-sm h-100",
                    ),
                    xs=12,
                    lg=6,
                    className="mb-4",
                ),
                dbc.Col(
                    dbc.Card(
                        [
                            dbc.CardHeader("Portfolio Sanity Trend", className="fw-bold"),
                            dbc.CardBody(
                                dcc.Graph(id="arb-value-fig", config={"displayModeBar": False})
                            ),
                        ],
                        className="shadow-sm h-100",
                    ),
                    xs=12,
                    lg=6,
                    className="mb-4",
                ),
            ]
        ),
        dbc.Row(
            [
                dbc.Col(
                    dbc.Card(
                        [
                            dbc.CardHeader(
                                "Latest Priced Holdings Composition",
                                className="fw-bold",
                            ),
                            dbc.CardBody(
                                dcc.Graph(
                                    id="arb-composition-fig",
                                    config={"displayModeBar": False},
                                )
                            ),
                        ],
                        className="shadow-sm h-100",
                    ),
                    xs=12,
                    lg=6,
                    className="mb-4",
                ),
                dbc.Col(
                    dbc.Card(
                        [
                            dbc.CardHeader(
                                "Missing Price Rows (Base Ingredients)",
                                className="fw-bold",
                            ),
                            dbc.CardBody(html.Div(id="arb-missing-price-table")),
                        ],
                        className="shadow-sm h-100",
                    ),
                    xs=12,
                    lg=6,
                    className="mb-4",
                ),
            ]
        ),
        dbc.Row(
            dbc.Col(
                dbc.Card(
                    [
                        dbc.CardHeader("Exception Rows (Overall)", className="fw-bold"),
                        dbc.CardBody(html.Div(id="arb-exception-table")),
                    ],
                    className="shadow-sm",
                ),
                xs=12,
                className="mb-4",
            )
        ),
        dbc.Row(
            dbc.Col(
                dbc.Card(
                    [
                        dbc.CardHeader("Latest 100 Transactions", className="fw-bold"),
                        dbc.CardBody(
                            [
                                dbc.Row(
                                    [
                                        dbc.Col(
                                            html.Small("Rows per page: 10", className="text-muted"),
                                            width="auto",
                                        ),
                                        dbc.Col(
                                            dcc.Dropdown(
                                                id="arb-latest-tx-page",
                                                options=[{"label": "Page 1", "value": 1}],
                                                value=1,
                                                clearable=False,
                                            ),
                                            md=3,
                                            xs=12,
                                        ),
                                    ],
                                    className="mb-3 align-items-center",
                                ),
                                html.Div(id="arb-latest-tx-table"),
                            ]
                        ),
                    ],
                    className="shadow-sm",
                ),
                xs=12,
                className="mb-4",
            )
        ),
    ],
    style={"padding": "20px", "backgroundColor": "#f8f9fa"},
)

register_arbitrum_trial_dashboard_callbacks(app=app)

if __name__ == "__main__":
    run_dash_app(app=app)
