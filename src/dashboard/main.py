import datetime

import dash_bootstrap_components as dbc
from dash import Dash, dcc, html

from dashboard.callbacks.nexo_dashboard import (
    NEXO_ANALYSIS_MODES,
    NEXO_COMPOSITION_MODES,
    register_nexo_dashboard_callbacks,
)
from dashboard.callbacks.real_estate_dashboard import register_real_estate_dashboard_callbacks
from dashboard.callbacks.stock_dashboard import (
    ANALYSIS_MODES,
    COMPOSITION_MODES,
    register_stock_dashboard_callbacks,
)
from dashboard.data_handling.real_estate_data import list_real_estate_assets
from dashboard.runtime import run_dash_app

# 1. Initialize App with Bootstrap
app = Dash(__name__, external_stylesheets=[dbc.themes.CERULEAN])


def _build_stock_tab() -> html.Div:
    return html.Div(
        [
            dcc.Store(id="stock-tx-page-store", data=0),
            dbc.Row(
                [
                    dbc.Col(
                        [
                            html.Label("Reference Date:", className="fw-bold"),
                            dcc.DatePickerSingle(
                                id="date-picker",
                                date=datetime.date.today(),
                                max_date_allowed=datetime.date.today(),
                                className="d-block",
                            ),
                        ],
                        xs=12,
                        md=2,
                        className="mb-3",
                    ),
                    dbc.Col(
                        [
                            html.Label("Analysis Level:", className="fw-bold"),
                            dcc.Dropdown(
                                id="analysis-mode",
                                options=ANALYSIS_MODES,
                                value="full",
                                clearable=False,
                            ),
                        ],
                        xs=12,
                        md=5,
                        className="mb-3",
                    ),
                    dbc.Col(
                        [
                            html.Label("Selection:", className="fw-bold"),
                            dcc.Dropdown(
                                id="asset-selector",
                                placeholder="Select...",
                                clearable=False,
                            ),
                        ],
                        xs=12,
                        md=5,
                        className="mb-3",
                    ),
                ],
                className="bg-light p-3 rounded shadow-sm mb-4 align-items-end",
            ),
            dbc.Row(
                dbc.Col(
                    dbc.Card(
                        dbc.CardBody(id="summary-stats", children="Select filters to see metrics"),
                        className="text-center shadow-sm mb-4 bg-primary text-white",
                    )
                )
            ),
            dbc.Row(
                [
                    dbc.Col(
                        dbc.Card(
                            [
                                dbc.CardHeader(
                                    "Portfolio Details",
                                    className="fw-bold",
                                    id="details-card-header",
                                ),
                                dbc.CardBody(
                                    [
                                        html.Div(
                                            [
                                                html.Label(
                                                    "Portfolio Composition By:",
                                                    className="fw-bold",
                                                ),
                                                dcc.Dropdown(
                                                    id="composition-mode",
                                                    options=COMPOSITION_MODES,
                                                    value="Asset Name",
                                                    clearable=False,
                                                ),
                                                html.Br(),
                                            ],
                                            id="composition-selector-wrapper",
                                        ),
                                        html.Div(id="portfolio-pie-container"),
                                    ],
                                    className="d-flex flex-column",
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
                                dbc.CardHeader("Value Over Time", className="fw-bold"),
                                dbc.CardBody(
                                    dcc.Graph(
                                        id="value-over-time", config={"displayModeBar": False}
                                    )
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
                            dbc.CardHeader("Quantity Over Time", className="fw-bold"),
                            dbc.CardBody(
                                dcc.Graph(
                                    id="quantity-over-time",
                                    config={"displayModeBar": False},
                                )
                            ),
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
                            dbc.CardHeader("Transactions (5 Per Page)", className="fw-bold"),
                            dbc.CardBody(
                                [
                                    dbc.Row(
                                        [
                                            dbc.Col(
                                                dbc.Button(
                                                    "Previous",
                                                    id="stock-tx-prev",
                                                    color="secondary",
                                                    outline=True,
                                                    size="sm",
                                                ),
                                                width="auto",
                                            ),
                                            dbc.Col(
                                                dbc.Button(
                                                    "Next",
                                                    id="stock-tx-next",
                                                    color="secondary",
                                                    outline=True,
                                                    size="sm",
                                                ),
                                                width="auto",
                                            ),
                                            dbc.Col(
                                                html.Div(
                                                    id="stock-tx-page-label",
                                                    className="text-muted small",
                                                ),
                                                className="d-flex align-items-center",
                                            ),
                                        ],
                                        className="mb-3 align-items-center",
                                    ),
                                    html.Div(id="stock-recent-transactions"),
                                ]
                            ),
                        ],
                        className="shadow-sm",
                    ),
                    xs=12,
                    className="mb-4",
                )
            ),
        ]
    )


def _build_real_estate_tab() -> html.Div:
    assets = list_real_estate_assets()
    asset_options = [{"label": "All Assets", "value": "ALL"}] + [
        {"label": asset_name, "value": asset_name} for asset_name in assets
    ]

    return html.Div(
        [
            dbc.Row(
                [
                    dbc.Col(
                        [
                            html.Label("As-of Date:", className="fw-bold"),
                            dcc.DatePickerSingle(
                                id="re-date-picker",
                                date=datetime.date.today(),
                                min_date_allowed=datetime.date(1900, 1, 1),
                                max_date_allowed=datetime.date(2100, 12, 31),
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
                                id="re-asset-selector",
                                options=asset_options,
                                value="ALL",
                                clearable=False,
                            ),
                        ],
                        xs=12,
                        md=8,
                        className="mb-3",
                    ),
                ],
                className="bg-light p-3 rounded shadow-sm mb-4 align-items-end",
            ),
            html.Div(id="re-status"),
            html.Div(id="re-summary-cards", className="mb-2"),
            dbc.Row(
                [
                    dbc.Col(
                        dbc.Card(
                            [
                                dbc.CardHeader("Value and Equity", className="fw-bold"),
                                dbc.CardBody(
                                    dcc.Graph(
                                        id="re-net-worth-chart",
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
                                dbc.CardHeader("Monthly Cashflow", className="fw-bold"),
                                dbc.CardBody(
                                    dcc.Graph(
                                        id="re-cashflow-chart",
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
                ]
            ),
            dbc.Row(
                [
                    dbc.Col(
                        dbc.Card(
                            [
                                dbc.CardHeader("P/L Breakdown", className="fw-bold"),
                                dbc.CardBody(
                                    dcc.Graph(
                                        id="re-pl-breakdown-chart",
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
                                dbc.CardHeader("Mortgage Balances", className="fw-bold"),
                                dbc.CardBody(
                                    dcc.Graph(
                                        id="re-mortgage-balance-chart",
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
                ]
            ),
            dbc.Row(
                [
                    dbc.Col(
                        dbc.Card(
                            [
                                dbc.CardHeader("Inflow Breakdown", className="fw-bold"),
                                dbc.CardBody(
                                    dcc.Graph(
                                        id="re-inflow-breakdown-chart",
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
                                dbc.CardHeader("Outflow Breakdown", className="fw-bold"),
                                dbc.CardBody(
                                    dcc.Graph(
                                        id="re-breakdown-chart",
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
                ]
            ),
            dbc.Row(
                dbc.Col(
                    dbc.Card(
                        [
                            dbc.CardHeader("Mortgage Summary", className="fw-bold"),
                            dbc.CardBody(html.Div(id="re-mortgage-table")),
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
                            dbc.CardHeader("Outflow Overview", className="fw-bold"),
                            dbc.CardBody(
                                [
                                    dbc.Row(
                                        [
                                            dbc.Col(
                                                html.Small(
                                                    "Rows shown",
                                                    className="text-muted",
                                                ),
                                                width="auto",
                                            ),
                                            dbc.Col(
                                                dcc.Dropdown(
                                                    id="re-outflow-row-limit",
                                                    options=[
                                                        {"label": "5", "value": 5},
                                                        {"label": "10", "value": 10},
                                                        {"label": "25", "value": 25},
                                                        {"label": "50", "value": 50},
                                                        {"label": "100", "value": 100},
                                                        {"label": "All", "value": "ALL"},
                                                    ],
                                                    value=5,
                                                    clearable=False,
                                                ),
                                                md=3,
                                                xs=12,
                                            ),
                                        ],
                                        className="mb-3 align-items-center",
                                    ),
                                    html.Div(id="re-recent-outflows"),
                                ]
                            ),
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
                            dbc.CardHeader("Inflow Overview", className="fw-bold"),
                            dbc.CardBody(
                                [
                                    dbc.Row(
                                        [
                                            dbc.Col(
                                                html.Small(
                                                    "Rows shown",
                                                    className="text-muted",
                                                ),
                                                width="auto",
                                            ),
                                            dbc.Col(
                                                dcc.Dropdown(
                                                    id="re-inflow-row-limit",
                                                    options=[
                                                        {"label": "5", "value": 5},
                                                        {"label": "10", "value": 10},
                                                        {"label": "25", "value": 25},
                                                        {"label": "50", "value": 50},
                                                        {"label": "100", "value": 100},
                                                        {"label": "All", "value": "ALL"},
                                                    ],
                                                    value=5,
                                                    clearable=False,
                                                ),
                                                md=3,
                                                xs=12,
                                            ),
                                        ],
                                        className="mb-3 align-items-center",
                                    ),
                                    html.Div(id="re-recent-inflows"),
                                ]
                            ),
                        ],
                        className="shadow-sm",
                    ),
                    xs=12,
                    className="mb-4",
                )
            ),
        ]
    )


def _build_nexo_tab() -> html.Div:
    return html.Div(
        [
            dcc.Store(id="nexo-tx-page-store", data=0),
            dbc.Row(
                [
                    dbc.Col(
                        [
                            html.Label("Reference Date:", className="fw-bold"),
                            dcc.DatePickerSingle(
                                id="nexo-date-picker",
                                date=datetime.date.today(),
                                max_date_allowed=datetime.date.today(),
                                className="d-block",
                            ),
                        ],
                        xs=12,
                        md=2,
                        className="mb-3",
                    ),
                    dbc.Col(
                        [
                            html.Label("Analysis Level:", className="fw-bold"),
                            dcc.Dropdown(
                                id="nexo-analysis-mode",
                                options=NEXO_ANALYSIS_MODES,
                                value="full",
                                clearable=False,
                            ),
                        ],
                        xs=12,
                        md=5,
                        className="mb-3",
                    ),
                    dbc.Col(
                        [
                            html.Label("Selection:", className="fw-bold"),
                            dcc.Dropdown(
                                id="nexo-asset-selector",
                                placeholder="Select...",
                                clearable=False,
                            ),
                        ],
                        xs=12,
                        md=5,
                        className="mb-3",
                    ),
                ],
                className="bg-light p-3 rounded shadow-sm mb-4 align-items-end",
            ),
            dbc.Row(
                dbc.Col(
                    dbc.Card(
                        dbc.CardBody(
                            id="nexo-summary-stats",
                            children="Select filters to see metrics",
                        ),
                        className="text-center shadow-sm mb-4 bg-primary text-white",
                    )
                )
            ),
            dbc.Row(
                [
                    dbc.Col(
                        dbc.Card(
                            [
                                dbc.CardHeader("Portfolio Details", className="fw-bold"),
                                dbc.CardBody(
                                    [
                                        html.Div(
                                            [
                                                html.Label(
                                                    "Portfolio Composition By:",
                                                    className="fw-bold",
                                                ),
                                                dcc.Dropdown(
                                                    id="nexo-composition-mode",
                                                    options=NEXO_COMPOSITION_MODES,
                                                    value="name",
                                                    clearable=False,
                                                ),
                                                html.Br(),
                                            ],
                                            id="nexo-composition-selector-wrapper",
                                        ),
                                        html.Div(id="nexo-portfolio-pie-container"),
                                    ],
                                    className="d-flex flex-column",
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
                                dbc.CardHeader("Value Over Time", className="fw-bold"),
                                dbc.CardBody(
                                    dcc.Graph(
                                        id="nexo-value-over-time",
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
                ]
            ),
            dbc.Row(
                dbc.Col(
                    dbc.Card(
                        [
                            dbc.CardHeader("Quantity Over Time", className="fw-bold"),
                            dbc.CardBody(
                                dcc.Graph(
                                    id="nexo-quantity-over-time",
                                    config={"displayModeBar": False},
                                )
                            ),
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
                            dbc.CardHeader("Transactions (5 Per Page)", className="fw-bold"),
                            dbc.CardBody(
                                [
                                    dbc.Row(
                                        [
                                            dbc.Col(
                                                dbc.Button(
                                                    "Previous",
                                                    id="nexo-tx-prev",
                                                    color="secondary",
                                                    outline=True,
                                                    size="sm",
                                                ),
                                                width="auto",
                                            ),
                                            dbc.Col(
                                                dbc.Button(
                                                    "Next",
                                                    id="nexo-tx-next",
                                                    color="secondary",
                                                    outline=True,
                                                    size="sm",
                                                ),
                                                width="auto",
                                            ),
                                            dbc.Col(
                                                html.Div(
                                                    id="nexo-tx-page-label",
                                                    className="text-muted small",
                                                ),
                                                className="d-flex align-items-center",
                                            ),
                                        ],
                                        className="mb-3 align-items-center",
                                    ),
                                    html.Div(id="nexo-recent-transactions"),
                                ]
                            ),
                        ],
                        className="shadow-sm",
                    ),
                    xs=12,
                    className="mb-4",
                )
            ),
        ]
    )


app.layout = dbc.Container(
    fluid=True,
    children=[
        dbc.Row(
            dbc.Col(
                html.H1("Investment Portfolio Dashboard", className="text-center my-4 text-primary")
            )
        ),
        dbc.Tabs(
            [
                dbc.Tab(_build_stock_tab(), label="Stocks", tab_id="stocks"),
                dbc.Tab(_build_nexo_tab(), label="NEXO", tab_id="nexo"),
                dbc.Tab(_build_real_estate_tab(), label="Real Estate", tab_id="real-estate"),
            ],
            active_tab="stocks",
            class_name="mb-3",
        ),
    ],
    style={"padding": "20px", "backgroundColor": "#f8f9fa"},
)

# 4. Register Callbacks
register_stock_dashboard_callbacks(app)
register_nexo_dashboard_callbacks(app)
register_real_estate_dashboard_callbacks(app)

if __name__ == "__main__":
    run_dash_app(app=app)
