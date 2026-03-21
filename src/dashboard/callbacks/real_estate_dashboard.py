from __future__ import annotations

import dash_bootstrap_components as dbc
import pandas as pd
import plotly.express as px
import plotly.graph_objs as go
from dash import Dash, Input, Output, html
from plotly.subplots import make_subplots

from dashboard.data_handling.real_estate_data import (
    build_monthly_cashflow_frame,
    build_mortgage_balance_frame,
    build_recent_inflows_frame,
    build_recent_outflows_frame,
    build_value_equity_frame,
    calculate_snapshot_metrics,
    filter_asset,
    load_real_estate_bundle,
    summarize_mortgages_from_rows,
)


def _format_currency(value: float) -> str:
    """
    Formats a numeric value in EUR.

    args:
        value: Numeric value.

    returns:
        Formatted EUR string.
    """
    return f"EUR {value:,.2f}"


def _empty_figure(title: str, message: str) -> go.Figure:
    """
    Creates an empty placeholder figure.

    args:
        title: Figure title.
        message: Placeholder message.

    returns:
        Placeholder figure.
    """
    figure = go.Figure()
    figure.update_layout(title=title, template="plotly_white", height=420)
    figure.add_annotation(
        text=message,
        x=0.5,
        y=0.5,
        xref="paper",
        yref="paper",
        showarrow=False,
        font={"size": 16},
    )
    return figure


def _build_summary_cards(metrics: dict[str, float], selected_date: str) -> dbc.Row:
    """
    Builds KPI summary cards for the real-estate tab.

    args:
        metrics: Snapshot metric dictionary.
        selected_date: As-of date.

    returns:
        KPI card row.
    """
    cards = [
        ("Property Value", _format_currency(metrics["property_value"]), "Latest WOZ as-of"),
        (
            "Outstanding Mortgage",
            _format_currency(metrics["outstanding_mortgage"]),
            "Remaining debt",
        ),
        ("Estimated Equity", _format_currency(metrics["estimated_equity"]), "Value - debt"),
        (
            "Net Cash Out",
            _format_currency(metrics["net_cash_out"]),
            "Costs + mortgage - inflows",
        ),
    ]

    columns = []
    for title, value, subtitle in cards:
        columns.append(
            dbc.Col(
                dbc.Card(
                    dbc.CardBody(
                        [
                            html.Div(title, className="text-muted"),
                            html.H4(value, className="mb-1"),
                            html.Small(subtitle, className="text-muted"),
                        ]
                    ),
                    className="shadow-sm h-100",
                ),
                xs=12,
                md=6,
                lg=4,
                xl=2,
                className="mb-3",
            )
        )

    return dbc.Row(
        [dbc.Col(html.Div(f"As-of: {selected_date}", className="text-muted mb-2"), width=12)]
        + columns
    )


def _build_status(errors: list[str]) -> html.Div:
    """
    Creates status alerts for loader warnings.

    args:
        errors: Loader errors.

    returns:
        Status component.
    """
    if not errors:
        return html.Div()

    return dbc.Alert(
        [
            html.Div("Some real-estate datasets could not be loaded:"),
            html.Ul([html.Li(err) for err in errors]),
        ],
        color="warning",
        className="mb-3",
    )


def _create_net_worth_figure(value_equity: pd.DataFrame) -> go.Figure:
    """
    Builds the value versus debt and equity timeline chart.

    args:
        value_equity: Value/equity timeline.

    returns:
        Line chart.
    """
    if value_equity.empty:
        return _empty_figure(
            title="Property Value vs Equity", message="No valuation data available"
        )

    figure = go.Figure()
    figure.add_trace(
        go.Scatter(
            x=value_equity["Date"],
            y=value_equity["Property Value"],
            mode="lines+markers",
            name="Property Value",
            marker={"size": 5},
        )
    )
    figure.add_trace(
        go.Scatter(
            x=value_equity["Date"],
            y=value_equity["Outstanding Mortgage"],
            mode="lines+markers",
            name="Outstanding Mortgage",
            marker={"size": 5},
        )
    )
    figure.add_trace(
        go.Scatter(
            x=value_equity["Date"],
            y=value_equity["Estimated Equity"],
            mode="lines+markers",
            name="Estimated Equity",
            line={"width": 4},
            marker={"size": 6},
        )
    )
    figure.update_layout(
        title="Property Value vs Equity",
        template="plotly_white",
        hovermode="x unified",
        height=420,
        yaxis_title="EUR",
    )
    return figure


def _create_cashflow_figure(monthly_cashflow: pd.DataFrame) -> go.Figure:
    """
    Builds the monthly cashflow chart.

    args:
        monthly_cashflow: Monthly cashflow frame.

    returns:
        Cashflow figure.
    """
    if monthly_cashflow.empty:
        return _empty_figure(title="Monthly Cashflow", message="No cashflow data available")

    figure = make_subplots(rows=2, cols=1, shared_xaxes=True, vertical_spacing=0.12)
    figure.add_trace(
        go.Bar(x=monthly_cashflow["Date"], y=monthly_cashflow["Inflows"], name="Inflows"),
        row=1,
        col=1,
    )
    figure.add_trace(
        go.Bar(
            x=monthly_cashflow["Date"],
            y=-monthly_cashflow["Home Costs"],
            name="Home Costs",
        ),
        row=1,
        col=1,
    )
    figure.add_trace(
        go.Bar(
            x=monthly_cashflow["Date"],
            y=-monthly_cashflow["Mortgage Interest"],
            name="Mortgage Interest",
        ),
        row=1,
        col=1,
    )
    figure.add_trace(
        go.Bar(
            x=monthly_cashflow["Date"],
            y=-monthly_cashflow["Mortgage Repayment"],
            name="Mortgage Repayment",
        ),
        row=1,
        col=1,
    )
    figure.add_trace(
        go.Scatter(
            x=monthly_cashflow["Date"],
            y=monthly_cashflow["Net Cash Flow"],
            mode="lines",
            name="Net Monthly Cashflow",
            line={"width": 3, "color": "#111111"},
        ),
        row=1,
        col=1,
    )
    figure.add_trace(
        go.Scatter(
            x=monthly_cashflow["Date"],
            y=monthly_cashflow["Cumulative Net Cash Flow"],
            mode="lines",
            name="Cumulative Net Cashflow",
            line={"width": 3, "color": "#1f77b4"},
        ),
        row=2,
        col=1,
    )

    figure.update_layout(
        title="Monthly Cashflow",
        barmode="relative",
        template="plotly_white",
        height=520,
        hovermode="x unified",
    )
    figure.update_yaxes(title_text="Monthly EUR", row=1, col=1)
    figure.update_yaxes(title_text="Cumulative EUR", row=2, col=1)
    return figure


def _create_mortgage_balance_figure(balance_frame: pd.DataFrame) -> go.Figure:
    """
    Builds the mortgage balance timeline chart.

    args:
        balance_frame: Mortgage balance timeline.

    returns:
        Balance line chart.
    """
    if balance_frame.empty:
        return _empty_figure(title="Mortgage Balances", message="No mortgage data available")

    figure = go.Figure()
    for mortgage_id in sorted(balance_frame["Mortgage ID"].unique()):
        mortgage_rows = balance_frame[balance_frame["Mortgage ID"] == mortgage_id]
        line_width = 4 if mortgage_id == "TOTAL" else 2
        figure.add_trace(
            go.Scatter(
                x=mortgage_rows["Date"],
                y=mortgage_rows["Outstanding Principal"],
                mode="lines",
                name=mortgage_id,
                line={"width": line_width},
                hovertemplate=(
                    "Mortgage: %{fullData.name}<br>"
                    "Date: %{x|%Y-%m-%d}<br>"
                    "Outstanding: EUR %{y:,.2f}<extra></extra>"
                ),
            )
        )

    figure.update_layout(
        title="Mortgage Balances Over Time",
        template="plotly_white",
        hovermode="x unified",
        height=420,
        yaxis_title="Outstanding EUR",
    )
    return figure


def _create_breakdown_figure(costs: pd.DataFrame, mortgages: pd.DataFrame) -> go.Figure:
    """
    Builds outflow composition chart.

    args:
        costs: Home costs.
        mortgages: Mortgage rows.

    returns:
        Pie chart.
    """
    breakdown_rows: list[dict[str, str | float]] = []

    if not costs.empty:
        grouped_costs = costs.groupby("Cost Type", as_index=False)["Amount"].sum()
        for _, row in grouped_costs.iterrows():
            breakdown_rows.append(
                {"Category": f"Cost: {row['Cost Type']}", "Amount": row["Amount"]}
            )

    if not mortgages.empty:
        payment_rows = mortgages[mortgages["Entry Type"] == "PAYMENT"]
        breakdown_rows.append(
            {
                "Category": "Mortgage Interest",
                "Amount": float(payment_rows["Interest Paid"].sum()),
            }
        )
        breakdown_rows.append(
            {
                "Category": "Mortgage Repayment",
                "Amount": float(payment_rows["Principal Repaid"].sum()),
            }
        )

    if not breakdown_rows:
        return _empty_figure(title="Outflow Breakdown", message="No outflow data available")

    breakdown = pd.DataFrame(breakdown_rows)
    breakdown = breakdown[breakdown["Amount"] > 0]
    if breakdown.empty:
        return _empty_figure(title="Outflow Breakdown", message="No outflow data available")

    figure = px.pie(breakdown, values="Amount", names="Category", title="Outflow Breakdown")
    figure.update_layout(template="plotly_white", height=420)
    return figure


def _create_inflow_breakdown_figure(inflows: pd.DataFrame) -> go.Figure:
    """
    Builds inflow composition chart.

    args:
        inflows: Inflow rows.

    returns:
        Pie chart.
    """
    if inflows.empty:
        return _empty_figure(title="Inflow Breakdown", message="No inflow data available")

    grouped = inflows.groupby("Inflow Type", as_index=False)["Amount"].sum()
    grouped = grouped[grouped["Amount"] > 0]
    if grouped.empty:
        return _empty_figure(title="Inflow Breakdown", message="No inflow data available")

    figure = px.pie(grouped, values="Amount", names="Inflow Type", title="Inflow Breakdown")
    figure.update_layout(template="plotly_white", height=420)
    return figure


def _create_pl_breakdown_figure(
    value_equity: pd.DataFrame, monthly_cashflow: pd.DataFrame
) -> go.Figure:
    """
    Builds P/L over-time chart from equity and cumulative cashflow.

    args:
        value_equity: Value/equity timeline.
        monthly_cashflow: Monthly cashflow frame.

    returns:
        Line chart.
    """
    if value_equity.empty and monthly_cashflow.empty:
        return _empty_figure(title="P/L Over Time", message="No equity/cashflow history available")

    equity_frame = (
        value_equity[["Date", "Estimated Equity"]]
        if not value_equity.empty
        else pd.DataFrame(columns=["Date", "Estimated Equity"])
    )
    cashflow_frame = (
        monthly_cashflow[["Date", "Cumulative Net Cash Flow"]]
        if not monthly_cashflow.empty
        else pd.DataFrame(columns=["Date", "Cumulative Net Cash Flow"])
    )

    merged = pd.merge(
        left=equity_frame,
        right=cashflow_frame,
        on="Date",
        how="outer",
    ).sort_values(by="Date")

    if "Estimated Equity" not in merged.columns:
        merged["Estimated Equity"] = 0.0
    if "Cumulative Net Cash Flow" not in merged.columns:
        merged["Cumulative Net Cash Flow"] = 0.0

    merged["Estimated Equity"] = pd.to_numeric(merged["Estimated Equity"], errors="coerce")
    merged["Cumulative Net Cash Flow"] = pd.to_numeric(
        merged["Cumulative Net Cash Flow"], errors="coerce"
    )
    merged["Estimated Equity"] = merged["Estimated Equity"].ffill().fillna(0.0)
    merged["Cumulative Net Cash Flow"] = merged["Cumulative Net Cash Flow"].ffill().fillna(0.0)
    merged["Total P/L"] = merged["Estimated Equity"] + merged["Cumulative Net Cash Flow"]

    figure = go.Figure()
    figure.add_trace(
        go.Scatter(
            x=merged["Date"],
            y=merged["Estimated Equity"],
            mode="lines+markers",
            name="Estimated Equity",
        )
    )
    figure.add_trace(
        go.Scatter(
            x=merged["Date"],
            y=merged["Cumulative Net Cash Flow"],
            mode="lines+markers",
            name="Cumulative Cashflow",
        )
    )
    figure.add_trace(
        go.Scatter(
            x=merged["Date"],
            y=merged["Total P/L"],
            mode="lines+markers",
            name="Total P/L",
            line={"width": 4},
        )
    )
    figure.update_layout(
        title="P/L Over Time (Equity + Cumulative Cashflow)",
        template="plotly_white",
        height=420,
        hovermode="x unified",
        yaxis_title="EUR",
    )
    return figure


def _create_mortgage_table(summary: pd.DataFrame) -> html.Div:
    """
    Builds mortgage summary table.

    args:
        summary: Mortgage summary frame.

    returns:
        Table component.
    """
    if summary.empty:
        return html.Div("No mortgage summary available.")

    table = summary.copy()
    numeric_columns = [
        "Initial Principal",
        "Interest Paid",
        "Principal Repaid",
        "Outstanding Principal",
        "Cash Out",
    ]
    for column in numeric_columns:
        table[column] = table[column].map(_format_currency)

    return dbc.Table.from_dataframe(
        df=table,
        striped=True,
        bordered=True,
        hover=True,
        size="sm",
        class_name="mb-0",
    )


def _create_recent_flow_table(flows: pd.DataFrame, empty_message: str) -> html.Div:
    """
    Builds a compact table for recent in/outflows.

    args:
        flows: Flow rows with Date, Asset, Type, Amount.
        empty_message: Message for empty table.

    returns:
        Table component.
    """
    if flows.empty:
        return html.Div(empty_message)

    table = flows.copy()
    table["Date"] = pd.to_datetime(table["Date"]).dt.strftime("%Y-%m-%d")
    table["Amount"] = table["Amount"].map(_format_currency)
    return dbc.Table.from_dataframe(
        df=table,
        striped=True,
        bordered=True,
        hover=True,
        size="sm",
        class_name="mb-0",
    )


def _resolve_row_limit(limit_value: str | int | None) -> int | None:
    """
    Resolves row-limit dropdown values.

    args:
        limit_value: Raw limit input.

    returns:
        Integer row limit, or None for all rows.
    """
    if limit_value in [None, "", "ALL"]:
        return None if limit_value == "ALL" else 5

    try:
        return int(limit_value)
    except (TypeError, ValueError):
        return 5


def register_real_estate_dashboard_callbacks(app: Dash) -> None:
    @app.callback(
        [
            Output("re-summary-cards", "children"),
            Output("re-net-worth-chart", "figure"),
            Output("re-cashflow-chart", "figure"),
            Output("re-mortgage-balance-chart", "figure"),
            Output("re-breakdown-chart", "figure"),
            Output("re-inflow-breakdown-chart", "figure"),
            Output("re-pl-breakdown-chart", "figure"),
            Output("re-mortgage-table", "children"),
            Output("re-recent-outflows", "children"),
            Output("re-recent-inflows", "children"),
            Output("re-status", "children"),
        ],
        [
            Input("re-date-picker", "date"),
            Input("re-asset-selector", "value"),
            Input("re-outflow-row-limit", "value"),
            Input("re-inflow-row-limit", "value"),
        ],
    )
    def update_real_estate_dashboard(
        selected_date: str,
        selected_asset: str,
        outflow_limit_value: str | int | None,
        inflow_limit_value: str | int | None,
    ):
        asof_date = selected_date or pd.Timestamp.today().strftime("%Y-%m-%d")
        asset = selected_asset or "ALL"
        outflow_limit = _resolve_row_limit(limit_value=outflow_limit_value)
        inflow_limit = _resolve_row_limit(limit_value=inflow_limit_value)

        bundle = load_real_estate_bundle(asof_date=asof_date)
        costs = filter_asset(frame=bundle.costs, asset=asset)
        inflows = filter_asset(frame=bundle.inflows, asset=asset)
        values = filter_asset(frame=bundle.values, asset=asset)
        mortgages = filter_asset(frame=bundle.mortgages, asset=asset)

        metrics = calculate_snapshot_metrics(
            costs=costs, inflows=inflows, values=values, mortgages=mortgages
        )
        summary_cards = _build_summary_cards(metrics=metrics, selected_date=asof_date)

        monthly_cashflow = build_monthly_cashflow_frame(
            costs=costs, inflows=inflows, mortgages=mortgages
        )
        mortgage_balance = build_mortgage_balance_frame(mortgages=mortgages)
        value_equity = build_value_equity_frame(
            values=values, mortgages=mortgages, asof_date=asof_date
        )
        mortgage_summary = summarize_mortgages_from_rows(mortgages=mortgages)
        recent_outflows = build_recent_outflows_frame(
            costs=costs, mortgages=mortgages, n=outflow_limit
        )
        recent_inflows = build_recent_inflows_frame(inflows=inflows, n=inflow_limit)

        net_worth_figure = _create_net_worth_figure(value_equity=value_equity)
        cashflow_figure = _create_cashflow_figure(monthly_cashflow=monthly_cashflow)
        mortgage_figure = _create_mortgage_balance_figure(balance_frame=mortgage_balance)
        breakdown_figure = _create_breakdown_figure(costs=costs, mortgages=mortgages)
        inflow_breakdown_figure = _create_inflow_breakdown_figure(inflows=inflows)
        pl_breakdown_figure = _create_pl_breakdown_figure(
            value_equity=value_equity, monthly_cashflow=monthly_cashflow
        )
        mortgage_table = _create_mortgage_table(summary=mortgage_summary)
        recent_outflows_table = _create_recent_flow_table(
            flows=recent_outflows, empty_message="No outflow rows available."
        )
        recent_inflows_table = _create_recent_flow_table(
            flows=recent_inflows, empty_message="No inflow rows available."
        )
        status = _build_status(errors=bundle.errors)

        return (
            summary_cards,
            net_worth_figure,
            cashflow_figure,
            mortgage_figure,
            breakdown_figure,
            inflow_breakdown_figure,
            pl_breakdown_figure,
            mortgage_table,
            recent_outflows_table,
            recent_inflows_table,
            status,
        )
