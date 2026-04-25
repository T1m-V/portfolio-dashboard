from __future__ import annotations

from enum import StrEnum

import dash_bootstrap_components as dbc
import pandas as pd
import plotly.express as px
import plotly.graph_objs as go
from dash import Dash, Input, Output, State, ctx, dcc, html
from plotly.subplots import make_subplots

from dashboard.data_handling.nexo_data import (
    list_nexo_coins,
    load_and_process_nexo_data,
    load_recent_nexo_transactions,
)
from file_paths import CURRENCY_METADATA


class NexoAnalysisType(StrEnum):
    FULL = "full"
    GROUP = "group"
    CURRENCY = "currency"
    NAME = "name"


NEXO_ANALYSIS_MODES = [
    {"label": "Full Portfolio", "value": NexoAnalysisType.FULL},
    {"label": "Asset Group", "value": NexoAnalysisType.GROUP},
    {"label": "Currency", "value": NexoAnalysisType.CURRENCY},
    {"label": "Single Asset", "value": NexoAnalysisType.NAME},
]

NEXO_COMPOSITION_MODES = [
    {"label": "Asset Name", "value": NexoAnalysisType.NAME},
    {"label": "Asset Group", "value": NexoAnalysisType.GROUP},
    {"label": "Currency", "value": NexoAnalysisType.CURRENCY},
]
PAGE_SIZE = 5


def _metadata_value(*, coin: str, mode: str) -> str:
    if mode == NexoAnalysisType.NAME:
        return coin
    if mode == NexoAnalysisType.GROUP:
        return str(CURRENCY_METADATA.get(coin, {}).get("group", "Unknown"))
    if mode == NexoAnalysisType.CURRENCY:
        return str(CURRENCY_METADATA.get(coin, {}).get("currency", "USD"))
    return ""


def fetch_nexo_data(
    selected_date: str,
    selection: str,
    mode: str,
) -> tuple[pd.DataFrame, str]:
    if mode == NexoAnalysisType.FULL:
        frame = load_and_process_nexo_data(end_date_str=selected_date)
        return frame, "NEXO Portfolio"

    if mode == NexoAnalysisType.NAME:
        frame = load_and_process_nexo_data(end_date_str=selected_date, coins=[selection])
        title = str(CURRENCY_METADATA.get(selection, {}).get("name", selection))
        return frame, title

    matching = resolve_nexo_coins(selection=selection, mode=mode)
    frame = load_and_process_nexo_data(end_date_str=selected_date, coins=matching)
    return frame, f"{mode.title()}: {selection}"


def resolve_nexo_coins(*, selection: str, mode: str) -> list[str]:
    coins = list_nexo_coins()
    if mode == NexoAnalysisType.FULL:
        return coins
    if mode == NexoAnalysisType.NAME:
        return [selection]
    return [coin for coin in coins if _metadata_value(coin=coin, mode=mode) == selection]


def create_nexo_pie_chart(
    df: pd.DataFrame,
    mode: str,
    comp_mode: str,
    selection: str,
) -> html.Div:
    if df.empty:
        return html.Div("No data available")

    if mode == NexoAnalysisType.NAME:
        info = CURRENCY_METADATA.get(selection, {})
        rows = [
            html.Tr([html.Td("Ticker", className="fw-bold"), html.Td(info.get("ticker", "-"))]),
            html.Tr([html.Td("Symbol", className="fw-bold"), html.Td(selection)]),
            html.Tr([html.Td("Name", className="fw-bold"), html.Td(info.get("name", selection))]),
            html.Tr([html.Td("Group", className="fw-bold"), html.Td(info.get("group", "Unknown"))]),
            html.Tr(
                [html.Td("Currency", className="fw-bold"), html.Td(info.get("currency", "USD"))]
            ),
        ]
        return html.Div(
            [
                html.H5("Asset Details", className="text-center mb-3"),
                dbc.Table(
                    [html.Tbody(rows)],
                    bordered=True,
                    hover=True,
                    size="sm",
                    className="bg-white",
                ),
            ]
        )

    active_holdings = df[df["Quantity"].abs() > 0.00001].copy()
    if active_holdings.empty:
        return html.Div("No active holdings to display.")

    if comp_mode == NexoAnalysisType.NAME:
        active_holdings["composition_label"] = active_holdings["Asset Name"]
    elif comp_mode == NexoAnalysisType.GROUP:
        active_holdings["composition_label"] = active_holdings["Asset Group"]
    else:
        active_holdings["composition_label"] = active_holdings["Currency"]

    fig = px.pie(
        active_holdings,
        values="Market Value",
        names="composition_label",
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


def create_nexo_performance_line_chart(
    df: pd.DataFrame,
    selected_date: str,
    title_suffix: str,
) -> go.Figure:
    if df.empty:
        return go.Figure()

    dt = pd.to_datetime(selected_date)
    history_df = df[df["Date"] <= dt].copy()
    history_df["Invested Capital"] = (
        history_df["Principal Invested"]
        + history_df["Cumulative Fees"]
        + history_df["Cumulative Taxes"]
        - history_df["Gross Dividends"]
    )

    total_history = (
        history_df.groupby("Date")
        .agg({"Market Value": "sum", "Invested Capital": "sum"})
        .reset_index()
    )
    total_history["Profit/Loss"] = total_history["Market Value"] - total_history["Invested Capital"]

    fig = make_subplots(
        rows=2,
        cols=1,
        shared_xaxes=True,
        vertical_spacing=0.1,
        subplot_titles=(f"Performance | {title_suffix}", "Absolute Profit/Loss (EUR)"),
        row_heights=[0.7, 0.3],
    )

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


def generate_nexo_summary_stats(
    df: pd.DataFrame,
    selected_date: str,
    title_suffix: str,
) -> html.Div:
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
                f"Current Value: EUR{total_val:,.2f}",
                style={"fontWeight": "bold", "fontSize": "20px"},
            ),
            html.Div(
                f"Net Profit/Loss: EUR{total_pl:,.2f}",
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
                    html.P(f"Dividends: EUR{total_divs:,.2f}"),
                    html.P(f"Net Invested: EUR{net_invested:,.2f}"),
                    html.P(f"Fees: EUR{total_fees:,.2f}"),
                    html.P(f"Taxes: EUR{total_taxes:,.2f}"),
                ],
            ),
        ]
    )


def create_nexo_quantity_line_chart(
    df: pd.DataFrame,
    selected_date: str,
    title_suffix: str,
) -> go.Figure:
    if df.empty:
        return go.Figure()

    dt = pd.to_datetime(selected_date)
    history_df = df[df["Date"] <= dt].copy()
    quantity_history = history_df.groupby("Date").agg({"Quantity": "sum"}).reset_index()

    fig = go.Figure(
        data=[
            go.Scatter(
                x=quantity_history["Date"],
                y=quantity_history["Quantity"],
                name="Quantity",
                mode="lines",
            )
        ]
    )
    fig.update_layout(
        title=f"Quantity | {title_suffix}",
        height=320,
        hovermode="x unified",
        template="plotly_white",
        margin=dict(t=50, b=25, l=25, r=25),
    )
    return fig


def render_recent_nexo_transactions_table(tx: pd.DataFrame) -> html.Div:
    if tx.empty:
        return html.Div("No transactions found for this filter.")

    display = tx.copy()
    display["Input"] = (
        display["Input Amount"].astype(str) + " " + display["Input Currency"].astype(str)
    )
    display["Output"] = (
        display["Output Amount"].astype(str) + " " + display["Output Currency"].astype(str)
    )

    columns = ["Date", "Type", "Input", "Output", "USD Equivalent", "Details"]
    header = [html.Th(col) for col in columns]
    body = [html.Tr([html.Td(row[col]) for col in columns]) for _, row in display.iterrows()]

    return dbc.Table(
        [html.Thead(html.Tr(header)), html.Tbody(body)],
        bordered=True,
        hover=True,
        responsive=True,
        size="sm",
        className="mb-0",
    )


def register_nexo_dashboard_callbacks(app: Dash) -> None:
    @app.callback(
        [
            Output("nexo-portfolio-pie-container", "children"),
            Output("nexo-value-over-time", "figure"),
            Output("nexo-quantity-over-time", "figure"),
            Output("nexo-summary-stats", "children"),
            Output("nexo-composition-selector-wrapper", "style"),
        ],
        [
            Input("nexo-date-picker", "date"),
            Input("nexo-asset-selector", "value"),
            Input("nexo-analysis-mode", "value"),
            Input("nexo-composition-mode", "value"),
        ],
    )
    def update_nexo_dashboard(
        selected_date: str,
        selected_selection: str,
        mode: str,
        comp_mode: str,
    ) -> tuple[html.Div, go.Figure, go.Figure, html.Div, dict]:
        df_master, title_suffix = fetch_nexo_data(
            selected_date=selected_date,
            selection=selected_selection,
            mode=mode,
        )

        if df_master.empty:
            return (
                html.Div("No data"),
                go.Figure(),
                go.Figure(),
                html.Div("No data"),
                {"display": "block"},
            )

        df_final_snapshot = df_master[df_master["Date"] == pd.to_datetime(selected_date)]
        side_content = create_nexo_pie_chart(
            df=df_final_snapshot,
            mode=mode,
            comp_mode=comp_mode,
            selection=selected_selection,
        )
        line_fig = create_nexo_performance_line_chart(
            df=df_master,
            selected_date=selected_date,
            title_suffix=title_suffix,
        )
        quantity_fig = create_nexo_quantity_line_chart(
            df=df_master,
            selected_date=selected_date,
            title_suffix=title_suffix,
        )
        summary_div = generate_nexo_summary_stats(
            df=df_master,
            selected_date=selected_date,
            title_suffix=title_suffix,
        )
        comp_style = {"display": "none"} if mode == NexoAnalysisType.NAME else {"display": "block"}
        return side_content, line_fig, quantity_fig, summary_div, comp_style

    @app.callback(
        [
            Output("nexo-recent-transactions", "children"),
            Output("nexo-tx-page-store", "data"),
            Output("nexo-tx-page-label", "children"),
            Output("nexo-tx-prev", "disabled"),
            Output("nexo-tx-next", "disabled"),
        ],
        [
            Input("nexo-date-picker", "date"),
            Input("nexo-asset-selector", "value"),
            Input("nexo-analysis-mode", "value"),
            Input("nexo-tx-prev", "n_clicks"),
            Input("nexo-tx-next", "n_clicks"),
        ],
        [State("nexo-tx-page-store", "data")],
    )
    def update_nexo_transactions(
        selected_date: str,
        selected_selection: str,
        mode: str,
        _prev_clicks: int | None,
        _next_clicks: int | None,
        current_page: int | None,
    ) -> tuple[html.Div, int, str, bool, bool]:
        triggered = ctx.triggered_id
        page = int(current_page or 0)

        if triggered in {"nexo-date-picker", "nexo-asset-selector", "nexo-analysis-mode"}:
            page = 0
        elif triggered == "nexo-tx-prev":
            page = max(page - 1, 0)
        elif triggered == "nexo-tx-next":
            page += 1

        coins = (
            None
            if mode == NexoAnalysisType.FULL
            else resolve_nexo_coins(selection=selected_selection, mode=mode)
        )
        tx = load_recent_nexo_transactions(end_date_str=selected_date, coins=coins, limit=None)
        total = len(tx)
        max_page = max((total - 1) // PAGE_SIZE, 0) if total else 0
        page = min(page, max_page)

        start = page * PAGE_SIZE
        paged_tx = tx.iloc[start : start + PAGE_SIZE]
        table = render_recent_nexo_transactions_table(paged_tx)

        if total == 0:
            label = "No transactions"
            return table, 0, label, True, True

        shown_end = start + len(paged_tx)
        label = f"Showing {start + 1}-{shown_end} of {total}"
        prev_disabled = page <= 0
        next_disabled = page >= max_page
        return table, page, label, prev_disabled, next_disabled

    @app.callback(
        [
            Output("nexo-asset-selector", "options"),
            Output("nexo-asset-selector", "value"),
            Output("nexo-asset-selector", "disabled"),
            Output("nexo-composition-mode", "options"),
            Output("nexo-composition-mode", "value"),
        ],
        Input("nexo-analysis-mode", "value"),
    )
    def update_nexo_selection_options(mode: str):
        comp_options = [option for option in NEXO_COMPOSITION_MODES if option["value"] != mode]
        coins = list_nexo_coins()

        if mode == NexoAnalysisType.FULL:
            return [{"label": "", "value": ""}], "", True, comp_options, NexoAnalysisType.NAME

        if mode == NexoAnalysisType.NAME:
            options = [
                {"label": CURRENCY_METADATA.get(coin, {}).get("name", coin), "value": coin}
                for coin in coins
            ]
            first_val = options[0]["value"] if options else None
            return options, first_val, False, [], None

        values = sorted({_metadata_value(coin=coin, mode=mode) for coin in coins})
        options = [{"label": value, "value": value} for value in values]
        first_val = options[0]["value"] if options else None
        return options, first_val, False, comp_options, NexoAnalysisType.NAME
