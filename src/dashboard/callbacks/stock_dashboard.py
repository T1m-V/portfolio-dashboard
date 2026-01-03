import json
from enum import StrEnum
from pathlib import Path
from typing import Tuple

import dash_bootstrap_components as dbc
import pandas as pd
import plotly.express as px
import plotly.graph_objs as go
from dash import Dash, Input, Output, dcc, html
from plotly.subplots import make_subplots

from dashboard.data_handling.transaction_data import load_and_process_data_group_stocks

TICKER_MAP_PATH = Path(__file__).parents[3] / "data" / "ticker_map.json"


class AnalysisType(StrEnum):
    FULL = "full"
    GROUP = "group"
    REGION = "region"
    PROVIDER = "provider"
    NAME = "name"


# 2. Constants
ANALYSIS_MODES = [
    {"label": "Full Portfolio", "value": AnalysisType.FULL},
    {"label": "Asset Group", "value": AnalysisType.GROUP},
    {"label": "Region", "value": AnalysisType.REGION},
    {"label": "Provider", "value": AnalysisType.PROVIDER},
    {"label": "Single Asset", "value": AnalysisType.NAME},
]

COMPOSITION_MODES = [
    {"label": "Asset Name", "value": AnalysisType.NAME},
    {"label": "Asset Group", "value": AnalysisType.GROUP},
    {"label": "Region", "value": AnalysisType.REGION},
    {"label": "Provider", "value": AnalysisType.PROVIDER},
]

with open(TICKER_MAP_PATH, "r") as f:
    TICKER_MAP: dict[str, dict[str, str]] = json.load(f)


def fetch_portfolio_data(selected_date: str, selection: str, mode: str) -> Tuple[pd.DataFrame, str]:
    """
    Loads and filters the master dataframe based on the analysis mode.
    Returns the dataframe and a display title suffix.
    """
    if mode == AnalysisType.FULL:
        df = load_and_process_data_group_stocks(end_date_str=selected_date)
        return df, "Total Portfolio"

    elif mode == AnalysisType.NAME:
        df = load_and_process_data_group_stocks(end_date_str=selected_date, isins=[selection])
        title = TICKER_MAP.get(selection, {}).get("name", selection)
        return df, title

    else:
        isins_in_group = [isin for isin, info in TICKER_MAP.items() if info.get(mode) == selection]
        df = load_and_process_data_group_stocks(end_date_str=selected_date, isins=isins_in_group)
        return df, f"Group: {selection}"


def create_pie_chart(df: pd.DataFrame, mode: str, comp_mode: str, selection: str) -> html.Div:
    """
    Returns a Pie Chart if in Full/Group mode,
    or a Metadata Table if in Asset mode.
    """
    if df.empty:
        return html.Div("No data available")

    # --- Case A: Individual Asset (Show Metadata Table) ---
    if mode == AnalysisType.NAME:
        info = TICKER_MAP.get(selection, {})
        rows = [
            html.Tr([html.Td("Ticker", className="fw-bold"), html.Td(info.get("ticker", "-"))]),
            html.Tr([html.Td("ISIN", className="fw-bold"), html.Td(selection)]),
            html.Tr([html.Td("Region", className="fw-bold"), html.Td(info.get("region", "-"))]),
            html.Tr([html.Td("Asset Group", className="fw-bold"), html.Td(info.get("group", "-"))]),
            html.Tr([html.Td("Provider", className="fw-bold"), html.Td(info.get("provider", "-"))]),
        ]
        return html.Div(
            [
                html.H5("Asset Details", className="text-center mb-3"),
                dbc.Table(
                    [html.Tbody(rows)], bordered=True, hover=True, size="sm", className="bg-white"
                ),
            ]
        )

    # --- Case B: Portfolio/Group (Show Pie Chart) ---
    active_holdings = df[df["Quantity"] > 0.00001].copy()
    if active_holdings.empty:
        return html.Div("No active holdings to display.")

    # Enrich metadata for pie chart if missing
    if comp_mode not in active_holdings.columns:
        if "ISIN" in active_holdings.columns:
            active_holdings[comp_mode] = active_holdings["ISIN"].map(
                lambda x: TICKER_MAP.get(x, {}).get(comp_mode, "Unknown")
            )

    fig = px.pie(
        active_holdings,
        values="Market Value",
        names=comp_mode,
    )
    fig.update_layout(
        autosize=True,
        margin=dict(t=0, b=0, l=0, r=0),
        legend=dict(orientation="v", yanchor="middle", y=0.5, xanchor="left", x=1.0),
    )

    return html.Div(
        [
            dcc.Graph(
                figure=fig,
                config={"displayModeBar": False, "responsive": True},
                style={"width": "100%"},
            )
        ],
        className="w-100",
    )


def create_performance_line_chart(
    df: pd.DataFrame, selected_date: str, title_suffix: str
) -> go.Figure:
    """
    Generates the Market Value vs Invested Capital line chart.
    """
    if df.empty:
        return go.Figure()

    # Filter history up to selected date
    dt = pd.to_datetime(selected_date)
    history_df = df[df["Date"] <= dt].copy()

    # Calculate Invested Capital: Principal + Fees + Taxes - Dividends
    history_df["Invested Capital"] = (
        history_df["Principal Invested"]
        + history_df["Cumulative Fees"]
        + history_df["Cumulative Taxes"]
        - history_df["Gross Dividends"]
    )

    # Aggregate by Date
    total_history = (
        history_df.groupby("Date")
        .agg({"Market Value": "sum", "Invested Capital": "sum"})
        .reset_index()
    )
    total_history["Profit/Loss"] = total_history["Market Value"] - total_history["Invested Capital"]

    # Create Subplots
    fig = make_subplots(
        rows=2,
        cols=1,
        shared_xaxes=True,
        vertical_spacing=0.1,
        subplot_titles=(f"Performance | {title_suffix}", "Absolute Profit/Loss (€)"),
        row_heights=[0.7, 0.3],
    )

    # Row 1: Market Value vs Invested
    fig.add_trace(
        go.Scatter(x=total_history["Date"], y=total_history["Market Value"], name="Market Value"),
        row=1,
        col=1,
    )
    fig.add_trace(
        go.Scatter(
            x=total_history["Date"],
            y=total_history["Invested Capital"],
            name="Invested Capital",
            line=dict(dash="dash"),
        ),
        row=1,
        col=1,
    )

    # Row 2: Profit/Loss Area
    current_pl = total_history["Profit/Loss"].iloc[-1] if not total_history.empty else 0
    pl_color = "green" if current_pl >= 0 else "red"

    fig.add_trace(
        go.Scatter(
            x=total_history["Date"],
            y=total_history["Profit/Loss"],
            name="Profit/Loss",
            fill="tozeroy",
            line=dict(color=pl_color),
        ),
        row=2,
        col=1,
    )

    fig.update_layout(height=600, hovermode="x unified", template="plotly_white")
    return fig


def generate_summary_stats(df: pd.DataFrame, selected_date: str, title_suffix: str) -> html.Div:
    """
    Simplified: Returns ONLY the scalar metrics.
    """
    dt = pd.to_datetime(selected_date)
    day_df = df[df["Date"] == dt].copy()

    if day_df.empty:
        return html.Div("No data for selected date.")

    total_val = day_df["Market Value"].sum()
    total_divs = day_df["Gross Dividends"].sum()
    total_fees = day_df["Cumulative Fees"].sum()
    total_taxes = day_df["Cumulative Taxes"].sum()
    net_invested = day_df["Principal Invested"].sum() + total_fees + total_taxes - total_divs
    total_pl = total_val - net_invested

    return html.Div(
        [
            html.Div(
                f"Metrics for: {title_suffix}",
                style={"fontSize": "24px", "textDecoration": "underline"},
            ),
            html.Div(
                f"Current Value: €{total_val:,.2f}",
                style={"fontWeight": "bold", "fontSize": "20px"},
            ),
            html.Div(
                f"Net Profit/Loss: €{total_pl:,.2f}",
                style={"color": "green" if total_pl >= 0 else "red", "fontSize": "20px"},
            ),
            html.Hr(),
            html.Div(
                style={
                    "display": "flex",
                    "gap": "20px",
                    "justifyContent": "center",
                    "flexWrap": "wrap",
                },
                children=[
                    html.P(f"Dividends: €{total_divs:,.2f}"),
                    html.P(f"Net Invested: €{net_invested:,.2f}"),
                    html.P(f"Fees: €{total_fees:,.2f}"),
                    html.P(f"Taxes: €{total_taxes:,.2f}"),
                ],
            ),
        ]
    )


# --- 3. Main Callbacks ---


def register_stock_dashboard_callbacks(app: Dash):
    @app.callback(
        [
            Output("portfolio-pie-container", "children"),
            Output("value-over-time", "figure"),
            Output("summary-stats", "children"),
            Output("composition-selector-wrapper", "style"),
        ],
        [
            Input("date-picker", "date"),
            Input("asset-selector", "value"),
            Input("analysis-mode", "value"),
            Input("composition-mode", "value"),
        ],
    )
    def update_dashboard(
        selected_date: str, selected_selection: str, mode: str, comp_mode: str
    ) -> tuple[html.Div, go.Figure, html.Div]:
        df_master, title_suffix = fetch_portfolio_data(selected_date, selected_selection, mode)

        if df_master.empty:
            return html.Div("No data"), go.Figure(), html.Div("No data")

        # 1. Create the left-side content (Pie or Table)
        df_final_snapshot = df_master[df_master["Date"] == selected_date]
        side_content = create_pie_chart(
            df=df_final_snapshot, mode=mode, comp_mode=comp_mode, selection=selected_selection
        )

        # 2. Performance Line Chart
        line_fig = create_performance_line_chart(
            df=df_master, selected_date=selected_date, title_suffix=title_suffix
        )

        # 3. Summary Stats (Top Bar)
        summary_div = generate_summary_stats(
            df=df_master, selected_date=selected_date, title_suffix=title_suffix
        )

        # Hide the "Composition By" dropdown if we are looking at a single asset
        comp_style = {"display": "none"} if mode == AnalysisType.NAME else {"display": "block"}

        return side_content, line_fig, summary_div, comp_style

    @app.callback(
        [
            Output("asset-selector", "options"),
            Output("asset-selector", "value"),
            Output("asset-selector", "disabled"),
            Output("composition-mode", "options"),
            Output("composition-mode", "value"),
        ],
        Input("analysis-mode", "value"),
    )
    def update_selection_options(mode):
        """
        Updates the dropdown options based on the analysis mode.
        """
        comp_options = [option for option in COMPOSITION_MODES if option["value"] != mode]

        if mode == AnalysisType.FULL:
            return [{"label": "", "value": ""}], "", True, comp_options, AnalysisType.NAME

        elif mode == AnalysisType.NAME:
            options = [
                {"label": info.get("name", isin), "value": isin}
                for isin, info in TICKER_MAP.items()
            ]
            first_val = options[0]["value"] if options else None
            return options, first_val, False, [], None

        else:
            groups = sorted(
                list(set(info.get(mode) for info in TICKER_MAP.values() if info.get(mode)))
            )
            options = [{"label": g, "value": g} for g in groups]
            first_val = options[0]["value"] if options else None
            return options, first_val, False, comp_options, AnalysisType.NAME
