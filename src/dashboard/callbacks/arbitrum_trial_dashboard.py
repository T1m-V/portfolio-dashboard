from __future__ import annotations

import functools

import dash_bootstrap_components as dbc
import pandas as pd
import plotly.express as px
import plotly.graph_objs as go
from dash import Dash, Input, Output, html
from plotly.subplots import make_subplots

from dashboard.data_handling.arbitrum_health_data import (
    TX_PAGE_SIZE,
    ArbitrumHealthBundle,
    build_dataset_freshness_frame,
    build_exception_daily_frame,
    build_exception_table_frame,
    build_holdings_valuation_frame,
    build_holdings_value_daily_frame,
    build_latest_health_metrics,
    build_latest_transactions_frame,
    build_missing_price_frame,
    build_route_mix_daily_frame,
    build_snapshot_valuation_frame,
    build_tx_daily_frame,
    filter_valuation_by_asset,
    list_invested_assets,
    load_arbitrum_health_bundle,
)

WINDOW_OPTIONS = {"30D": 30, "90D": 90, "180D": 180, "ALL": None}
STATUS_TO_COLOR = {"OK": "success", "WARN": "warning", "CRIT": "danger"}


@functools.lru_cache(maxsize=1)
def _load_cached_bundle() -> ArbitrumHealthBundle:
    return load_arbitrum_health_bundle()


@functools.lru_cache(maxsize=1)
def _load_cached_valuation() -> pd.DataFrame:
    return build_holdings_valuation_frame(bundle=_load_cached_bundle())


@functools.lru_cache(maxsize=1)
def _load_cached_snapshot_valuation() -> pd.DataFrame:
    return build_snapshot_valuation_frame(bundle=_load_cached_bundle())


def _empty_figure(title: str, message: str) -> go.Figure:
    figure = go.Figure()
    figure.update_layout(title=title, template="plotly_white", height=420)
    figure.add_annotation(
        text=message,
        x=0.5,
        y=0.5,
        xref="paper",
        yref="paper",
        showarrow=False,
        font={"size": 15},
    )
    return figure


def _status_badge(status: str) -> dbc.Badge:
    color = STATUS_TO_COLOR.get(status, "secondary")
    return dbc.Badge(status, color=color, className="ms-2")


def _format_currency(value: float) -> str:
    return f"EUR {value:,.2f}"


def _asset_options(bundle: ArbitrumHealthBundle, valuation: pd.DataFrame) -> list[dict[str, str]]:
    assets = list_invested_assets(
        valuation=valuation,
        base_ingredients=bundle.base_ingredients,
        exceptions=bundle.exceptions,
    )
    return [{"label": "All Assets", "value": "ALL"}] + [
        {"label": asset, "value": asset} for asset in assets
    ]


def _resolve_effective_date(
    selected_date: str | None,
    available_dates: pd.Series,
) -> pd.Timestamp | None:
    normalized_dates = pd.to_datetime(available_dates, errors="coerce").dropna().sort_values()
    if normalized_dates.empty:
        return None

    selected = pd.to_datetime(selected_date, errors="coerce")
    if pd.isna(selected):
        return pd.Timestamp(normalized_dates.iloc[-1]).normalize()
    selected = pd.Timestamp(selected).normalize()

    earlier_or_equal = normalized_dates[normalized_dates <= selected]
    if not earlier_or_equal.empty:
        return pd.Timestamp(earlier_or_equal.iloc[-1]).normalize()
    return pd.Timestamp(normalized_dates.iloc[0]).normalize()


def _window_start(end_date: pd.Timestamp, window: str, min_date: pd.Timestamp) -> pd.Timestamp:
    days = WINDOW_OPTIONS.get(window)
    if days is None:
        return min_date
    return max(min_date, end_date - pd.Timedelta(days=days - 1))


def _build_latest_tx_page_options(total_rows: int) -> list[dict[str, int]]:
    page_count = max(1, (total_rows + TX_PAGE_SIZE - 1) // TX_PAGE_SIZE)
    return [{"label": f"Page {index}", "value": index} for index in range(1, page_count + 1)]


def _slice_tx_page(latest_tx: pd.DataFrame, page: int) -> pd.DataFrame:
    if latest_tx.empty:
        return latest_tx.copy()
    safe_page = max(1, page)
    start = (safe_page - 1) * TX_PAGE_SIZE
    end = start + TX_PAGE_SIZE
    return latest_tx.iloc[start:end].copy()


def _build_metric_cards(
    metrics: dict[str, float | int | str],
    selected_value_eur: float,
    selected_value_date: pd.Timestamp | None,
) -> dbc.Row:
    selected_date_text = selected_value_date.strftime("%Y-%m-%d") if selected_value_date else "n/a"
    latest_holdings_date = str(metrics.get("latest_holdings_date", "")) or "n/a"
    card_specs = [
        (
            "Transactions Freshness",
            f"{metrics['transactions_freshness_lag_days']} days",
            str(metrics["transactions_freshness_status"]),
            "Lag vs today",
        ),
        (
            "Snapshot Freshness",
            f"{metrics['snapshot_freshness_lag_days']} days",
            str(metrics["snapshot_freshness_status"]),
            f"Latest snapshot date: {metrics['latest_snapshot_date']}",
        ),
        (
            "Pipeline Sync",
            f"{metrics['pipeline_sync_spread_days']} day spread",
            str(metrics["pipeline_sync_status"]),
            "Spread across tx/raw/snapshot datasets",
        ),
        (
            "Missing Prices (Overall)",
            str(metrics["missing_prices_overall_count"]),
            str(metrics["missing_prices_overall_status"]),
            "Across all available dates",
        ),
        (
            "Exceptions (Overall)",
            str(metrics["exceptions_overall_count"]),
            str(metrics["exceptions_overall_status"]),
            "Across all available dates",
        ),
        (
            "Estimated Portfolio Value",
            _format_currency(selected_value_eur),
            "OK",
            f"Selected date: {selected_date_text} | Latest holdings date: {latest_holdings_date}",
        ),
    ]

    columns = []
    for title, value, status, subtitle in card_specs:
        color = STATUS_TO_COLOR.get(status, "primary")
        columns.append(
            dbc.Col(
                dbc.Card(
                    dbc.CardBody(
                        [
                            html.Div([html.Span(title), _status_badge(status=status)]),
                            html.H4(value, className="mb-1 mt-2"),
                            html.Small(subtitle, className="text-white-50"),
                        ]
                    ),
                    color=color,
                    inverse=True,
                    className="h-100 shadow-sm",
                ),
                xs=12,
                md=6,
                xl=4,
                className="mb-3",
            )
        )
    return dbc.Row(columns)


def _build_status_alert(bundle: ArbitrumHealthBundle) -> html.Div:
    if not bundle.errors:
        return html.Div()
    return dbc.Alert(
        [
            html.Div("Some Arbitrum datasets failed to load:"),
            html.Ul([html.Li(error) for error in bundle.errors]),
        ],
        color="warning",
        className="mb-3",
    )


def _create_freshness_figure(freshness_frame: pd.DataFrame) -> go.Figure:
    if freshness_frame.empty:
        return _empty_figure(title="Dataset Freshness", message="No freshness data available")

    frame = freshness_frame.copy()
    frame["Lag Days"] = pd.to_numeric(frame["Lag Days"], errors="coerce").fillna(-1)
    frame["Status"] = frame["Status"].fillna("CRIT")
    figure = px.bar(
        frame,
        x="Dataset",
        y="Lag Days",
        color="Status",
        color_discrete_map={"OK": "#198754", "WARN": "#ffc107", "CRIT": "#dc3545"},
        title="Dataset Freshness (Lag Days)",
    )
    figure.update_layout(template="plotly_white", height=420, yaxis_title="Lag Days")
    return figure


def _create_tx_figure(tx_daily: pd.DataFrame) -> go.Figure:
    if tx_daily.empty:
        return _empty_figure(
            title="Transaction Activity",
            message="No transaction history available",
        )

    frame = tx_daily.copy()
    frame["Rolling Mean (7D)"] = frame["Tx Count"].rolling(window=7, min_periods=1).mean()

    figure = go.Figure()
    figure.add_trace(
        go.Bar(
            x=frame["Date"],
            y=frame["Tx Count"],
            name="Daily Transactions",
            marker={"color": "#4c78a8"},
        )
    )
    figure.add_trace(
        go.Scatter(
            x=frame["Date"],
            y=frame["Rolling Mean (7D)"],
            name="7D Rolling Mean",
            mode="lines",
            line={"width": 3, "color": "#f58518"},
        )
    )
    figure.update_layout(
        title="Daily Transaction Activity",
        template="plotly_white",
        height=420,
        hovermode="x unified",
        yaxis_title="Transactions",
    )
    return figure


def _create_exception_figure(exception_daily: pd.DataFrame) -> go.Figure:
    if exception_daily.empty:
        return _empty_figure(title="Daily Exceptions", message="No exception history available")

    figure = px.bar(
        exception_daily,
        x="Date",
        y="Count",
        color="Reason",
        title="Daily Composition Exceptions by Reason",
    )
    figure.update_layout(
        template="plotly_white",
        height=420,
        hovermode="x unified",
        yaxis_title="Exceptions",
        barmode="stack",
    )
    return figure


def _create_route_mix_figure(route_mix_daily: pd.DataFrame) -> go.Figure:
    if route_mix_daily.empty:
        return _empty_figure(
            title="Valuation Route Mix",
            message="No base-ingredient route data available",
        )

    figure = px.area(
        route_mix_daily,
        x="Date",
        y="EstimatedValueEUR",
        color="ValuationRoute",
        title="Valuation Route Mix (Absolute Estimated EUR)",
    )
    figure.update_layout(
        template="plotly_white",
        height=420,
        hovermode="x unified",
        yaxis_title="Absolute Estimated EUR",
    )
    return figure


def _create_value_figure(value_daily: pd.DataFrame) -> go.Figure:
    if value_daily.empty:
        return _empty_figure(
            title="Portfolio Value vs Principal", message="No holdings valuation data available"
        )

    frame = value_daily.sort_values("Date").copy()
    frame["Profit/Loss EUR"] = frame["Market Value EUR"] - frame["Principal Invested"]

    figure = make_subplots(
        rows=2,
        cols=1,
        shared_xaxes=True,
        vertical_spacing=0.12,
        subplot_titles=("Market Value vs Principal Invested", "Profit / Loss"),
        row_heights=[0.7, 0.3],
    )
    figure.add_trace(
        go.Scatter(x=frame["Date"], y=frame["Market Value EUR"], name="Market Value EUR"),
        row=1,
        col=1,
    )
    figure.add_trace(
        go.Scatter(
            x=frame["Date"],
            y=frame["Principal Invested"],
            name="Principal Invested",
            line={"dash": "dash"},
        ),
        row=1,
        col=1,
    )

    current_pl = float(frame["Profit/Loss EUR"].iloc[-1]) if not frame.empty else 0.0
    pl_color = "#198754" if current_pl >= 0 else "#dc3545"
    figure.add_trace(
        go.Scatter(
            x=frame["Date"],
            y=frame["Profit/Loss EUR"],
            name="Profit/Loss EUR",
            fill="tozeroy",
            line={"color": pl_color},
        ),
        row=2,
        col=1,
    )
    figure.update_layout(height=520, template="plotly_white", hovermode="x unified")
    return figure


def _create_composition_figure(
    valuation: pd.DataFrame,
    effective_date: pd.Timestamp | None,
) -> go.Figure:
    if effective_date is None or valuation.empty:
        return _empty_figure(title="Holdings Composition", message="No composition data available")

    frame = valuation[valuation["Date"] == effective_date].copy()
    if frame.empty:
        return _empty_figure(title="Holdings Composition", message="No rows for selected date")

    frame["Market Value EUR"] = pd.to_numeric(frame["Market Value EUR"], errors="coerce")
    frame = frame.dropna(subset=["Market Value EUR"])
    frame = frame[frame["Market Value EUR"] > 0]
    if frame.empty:
        return _empty_figure(title="Holdings Composition", message="No priced positive holdings")

    grouped = frame.groupby("Coin", as_index=False)["Market Value EUR"].sum()
    grouped = grouped.sort_values(by="Market Value EUR", ascending=False)
    top_n = 8
    if len(grouped) > top_n:
        top = grouped.head(top_n).copy()
        other_value = float(grouped.iloc[top_n:]["Market Value EUR"].sum())
        top = pd.concat(
            [top, pd.DataFrame([{"Coin": "Other", "Market Value EUR": other_value}])],
            ignore_index=True,
        )
        grouped = top

    figure = px.pie(
        grouped,
        values="Market Value EUR",
        names="Coin",
        title=f"Holdings Composition (Top 8) | {effective_date.strftime('%Y-%m-%d')}",
    )
    figure.update_layout(template="plotly_white", height=420)
    return figure


def _create_table(frame: pd.DataFrame, empty_message: str) -> html.Div:
    if frame.empty:
        return html.Div(empty_message)
    return dbc.Table.from_dataframe(
        df=frame,
        striped=True,
        bordered=True,
        hover=True,
        size="sm",
        class_name="mb-0",
    )


def register_arbitrum_trial_dashboard_callbacks(app: Dash) -> None:
    @app.callback(
        [
            Output("arb-asset-selector", "options"),
            Output("arb-asset-selector", "value"),
            Output("arb-kpi-cards", "children"),
            Output("arb-freshness-fig", "figure"),
            Output("arb-tx-fig", "figure"),
            Output("arb-exceptions-fig", "figure"),
            Output("arb-route-mix-fig", "figure"),
            Output("arb-value-fig", "figure"),
            Output("arb-composition-fig", "figure"),
            Output("arb-missing-price-table", "children"),
            Output("arb-exception-table", "children"),
            Output("arb-latest-tx-page", "options"),
            Output("arb-latest-tx-page", "value"),
            Output("arb-latest-tx-table", "children"),
            Output("arb-status", "children"),
        ],
        [
            Input("arb-date-picker", "date"),
            Input("arb-window", "value"),
            Input("arb-asset-selector", "value"),
            Input("arb-latest-tx-page", "value"),
        ],
    )
    def update_arbitrum_trial_dashboard(
        selected_date: str | None,
        window: str,
        selected_asset: str | None,
        tx_page: int | None,
    ):
        bundle = _load_cached_bundle()
        valuation_all = _load_cached_valuation()
        snapshot_valuation_all = _load_cached_snapshot_valuation()
        today = pd.Timestamp.today().normalize()

        asset_options = _asset_options(bundle=bundle, valuation=valuation_all)
        asset_values = {option["value"] for option in asset_options}
        effective_asset = selected_asset if selected_asset in asset_values else "ALL"
        valuation = filter_valuation_by_asset(
            valuation=valuation_all,
            selected_asset=effective_asset,
        )

        freshness = build_dataset_freshness_frame(bundle=bundle, today=today)
        tx_daily = build_tx_daily_frame(bundle=bundle, selected_asset=effective_asset)
        exception_daily = build_exception_daily_frame(
            bundle=bundle,
            selected_asset=effective_asset,
        )
        route_mix_daily = build_route_mix_daily_frame(
            bundle=bundle,
            selected_asset=effective_asset,
        )
        metrics = build_latest_health_metrics(
            bundle=bundle,
            today=today,
            selected_asset=effective_asset,
            valuation=valuation_all,
        )

        effective_date = _resolve_effective_date(
            selected_date=selected_date,
            available_dates=(
                valuation["Date"] if not valuation.empty else pd.Series(dtype="datetime64[ns]")
            ),
        )
        if effective_date is None and not freshness.empty:
            effective_date = _resolve_effective_date(
                selected_date=selected_date,
                available_dates=freshness["Latest Date"],
            )

        filtered_tx = tx_daily.copy()
        filtered_exceptions = exception_daily.copy()
        filtered_route_mix = route_mix_daily.copy()
        filtered_values = pd.DataFrame(columns=["Date", "Market Value EUR", "Principal Invested"])
        value_daily = build_holdings_value_daily_frame(
            bundle=bundle,
            selected_asset=effective_asset,
            valuation=valuation_all,
            snapshot_valuation=snapshot_valuation_all,
        )

        if effective_date is not None:
            if not tx_daily.empty:
                tx_start = _window_start(
                    end_date=effective_date,
                    window=window,
                    min_date=pd.Timestamp(tx_daily["Date"].min()),
                )
                filtered_tx = tx_daily[
                    (tx_daily["Date"] >= tx_start) & (tx_daily["Date"] <= effective_date)
                ].copy()

            if not exception_daily.empty:
                exception_start = _window_start(
                    end_date=effective_date,
                    window=window,
                    min_date=pd.Timestamp(exception_daily["Date"].min()),
                )
                filtered_exceptions = exception_daily[
                    (exception_daily["Date"] >= exception_start)
                    & (exception_daily["Date"] <= effective_date)
                ].copy()

            if not route_mix_daily.empty:
                route_start = _window_start(
                    end_date=effective_date,
                    window=window,
                    min_date=pd.Timestamp(route_mix_daily["Date"].min()),
                )
                filtered_route_mix = route_mix_daily[
                    (route_mix_daily["Date"] >= route_start)
                    & (route_mix_daily["Date"] <= effective_date)
                ].copy()

            if not value_daily.empty:
                value_start = _window_start(
                    end_date=effective_date,
                    window=window,
                    min_date=pd.Timestamp(value_daily["Date"].min()),
                )
                filtered_values = value_daily[
                    (value_daily["Date"] >= value_start) & (value_daily["Date"] <= effective_date)
                ].copy()

        selected_value = 0.0
        if effective_date is not None and not valuation.empty:
            selected_rows = valuation[valuation["Date"] == effective_date].copy()
            selected_value = float(
                pd.to_numeric(selected_rows["Market Value EUR"], errors="coerce").dropna().sum()
            )

        kpis = _build_metric_cards(
            metrics=metrics,
            selected_value_eur=selected_value,
            selected_value_date=effective_date,
        )
        freshness_fig = _create_freshness_figure(freshness_frame=freshness)
        tx_fig = _create_tx_figure(tx_daily=filtered_tx)
        exceptions_fig = _create_exception_figure(exception_daily=filtered_exceptions)
        route_mix_fig = _create_route_mix_figure(route_mix_daily=filtered_route_mix)
        value_fig = _create_value_figure(value_daily=filtered_values)
        composition_fig = _create_composition_figure(
            valuation=valuation,
            effective_date=effective_date,
        )

        missing_frame = build_missing_price_frame(
            bundle=bundle,
            selected_asset=effective_asset,
        )
        missing_frame["Date"] = missing_frame["Date"].astype(str)
        missing_frame["Quantity"] = pd.to_numeric(missing_frame["Quantity"], errors="coerce").round(
            8
        )
        missing_frame["EstimatedValueEUR"] = pd.to_numeric(
            missing_frame["EstimatedValueEUR"], errors="coerce"
        ).round(2)

        exception_frame = build_exception_table_frame(
            bundle=bundle,
            selected_asset=effective_asset,
        )
        exception_frame["EstimatedValueEUR"] = pd.to_numeric(
            exception_frame["EstimatedValueEUR"], errors="coerce"
        ).round(2)

        latest_tx = build_latest_transactions_frame(
            bundle=bundle,
            selected_asset=effective_asset,
        )
        page_options = _build_latest_tx_page_options(total_rows=len(latest_tx))
        max_page = len(page_options)
        page_value = tx_page if isinstance(tx_page, int) else 1
        page_value = min(max(1, page_value), max_page)
        latest_tx_page = _slice_tx_page(latest_tx=latest_tx, page=page_value)
        if "Fee" in latest_tx_page.columns:
            latest_tx_page["Fee"] = pd.to_numeric(latest_tx_page["Fee"], errors="coerce").round(8)

        missing_table = _create_table(
            frame=missing_frame,
            empty_message="No material missing-price rows for the selected asset.",
        )
        exception_table = _create_table(
            frame=exception_frame,
            empty_message="No exception rows for the selected asset.",
        )
        latest_tx_table = _create_table(
            frame=latest_tx_page,
            empty_message="No matching transactions for the selected asset.",
        )
        status = _build_status_alert(bundle=bundle)

        return (
            asset_options,
            effective_asset,
            kpis,
            freshness_fig,
            tx_fig,
            exceptions_fig,
            route_mix_fig,
            value_fig,
            composition_fig,
            missing_table,
            exception_table,
            page_options,
            page_value,
            latest_tx_table,
            status,
        )
