import datetime

import dash_bootstrap_components as dbc
from dash import Dash, dcc, html

from dashboard.callbacks.stock_dashboard import (
    ANALYSIS_MODES,
    COMPOSITION_MODES,
    register_stock_dashboard_callbacks,
)

# 1. Initialize App with Bootstrap
app = Dash(__name__, external_stylesheets=[dbc.themes.CERULEAN])


# 3. Layout Definition
app.layout = dbc.Container(
    fluid=True,
    children=[
        # --- Header ---
        dbc.Row(
            dbc.Col(
                html.H1("Investment Portfolio Dashboard", className="text-center my-4 text-primary")
            ),
        ),
        # --- Controls Section ---
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
                    md=3,
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
                    md=3,
                    className="mb-3",
                ),
                dbc.Col(
                    [
                        html.Label("Specific Selection:", className="fw-bold"),
                        dcc.Dropdown(
                            id="asset-selector",
                            placeholder="Select...",
                            clearable=False,
                        ),
                    ],
                    xs=12,
                    md=3,
                    className="mb-3",
                ),
                dbc.Col(
                    [
                        html.Label("Composition By:", className="fw-bold"),
                        dcc.Dropdown(
                            id="composition-mode",
                            options=COMPOSITION_MODES,
                            value="Asset Name",
                            clearable=False,
                        ),
                    ],
                    xs=12,
                    md=3,
                    className="mb-3",
                ),
            ],
            className="bg-light p-3 rounded shadow-sm mb-4 align-items-end",
        ),
        # --- Summary Stats ---
        dbc.Row(
            dbc.Col(
                dbc.Card(
                    dbc.CardBody(id="summary-stats", children="Select filters to see metrics"),
                    className="text-center shadow-sm mb-4 bg-primary text-white",
                )
            )
        ),
        # --- Charts ---
        dbc.Row(
            [
                # Pie Chart
                dbc.Col(
                    dbc.Card(
                        [
                            dbc.CardHeader(
                                "Portfolio Details", className="fw-bold", id="details-card-header"
                            ),
                            dbc.CardBody(
                                id="portfolio-pie-container",
                            ),
                        ],
                        className="shadow-sm h-100",
                    ),
                    xs=12,
                    lg=4,
                    className="mb-4",
                ),
                # Line Chart
                dbc.Col(
                    dbc.Card(
                        [
                            dbc.CardHeader("Value Over Time", className="fw-bold"),
                            dbc.CardBody(
                                dcc.Graph(id="value-over-time", config={"displayModeBar": False})
                            ),
                        ],
                        className="shadow-sm h-100",
                    ),
                    xs=12,
                    lg=8,
                    className="mb-4",
                ),
            ]
        ),
    ],
    style={"padding": "20px", "backgroundColor": "#f8f9fa"},
)

# 4. Register Callbacks
register_stock_dashboard_callbacks(app)

if __name__ == "__main__":
    app.run(debug=True)
