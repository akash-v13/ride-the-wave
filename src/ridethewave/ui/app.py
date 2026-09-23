"""Ride The Wave dashboard. Read-only view of the SQLite database the bot writes.

uv run streamlit run src/ridethewave/ui/app.py
"""

from __future__ import annotations

from datetime import datetime, timezone
from zoneinfo import ZoneInfo

import pandas as pd
import plotly.graph_objects as go
import streamlit as st

from ridethewave.config import load_settings
from ridethewave.ui import queries as q

ET = ZoneInfo("America/New_York")

# Colors: one categorical hue for series, a blue/red diverging pair for profit/loss polarity,
# text stays in Streamlit's own text color (never the series color).
BLUE = "#2a78d6"
RED = "#e34948"
GRID = "rgba(128,128,128,0.18)"

st.set_page_config(page_title="Ride The Wave", page_icon="🌊", layout="wide")
settings = load_settings()
DB_PATH = settings.storage.resolved_db_path()


def _fig_layout(fig: go.Figure, height: int = 300, y_title: str = "") -> go.Figure:
    fig.update_layout(
        height=height,
        margin=dict(l=8, r=8, t=8, b=8),
        paper_bgcolor="rgba(0,0,0,0)",
        plot_bgcolor="rgba(0,0,0,0)",
        hovermode="x unified",
        showlegend=False,
        xaxis=dict(showgrid=False, zeroline=False),
        yaxis=dict(gridcolor=GRID, zeroline=False, title=y_title),
    )
    return fig


def line_chart(df: pd.DataFrame, x: str, y: str, y_title: str = "", height: int = 300) -> go.Figure:
    fig = go.Figure(
        go.Scatter(
            x=df[x],
            y=df[y],
            mode="lines",
            line=dict(color=BLUE, width=2),
            hovertemplate="%{x|%b %d %H:%M}<br>%{y:$,.2f}<extra></extra>",
        )
    )
    return _fig_layout(fig, height, y_title)


def pnl_bars(df: pd.DataFrame, x: str, y: str, height: int = 260) -> go.Figure:
    colors = [BLUE if v >= 0 else RED for v in df[y]]
    fig = go.Figure(
        go.Bar(
            x=df[x],
            y=df[y],
            marker=dict(color=colors, line=dict(width=0)),
            hovertemplate="%{x}<br>%{y:$,.2f}<extra></extra>",
        )
    )
    fig.update_traces(marker_cornerradius=4)
    fig = _fig_layout(fig, height, "P/L ($)")
    fig.update_layout(bargap=0.35)
    return fig


def money(v) -> str:
    return "—" if v is None or pd.isna(v) else f"${v:,.2f}"


def signed(v) -> str:
    return "—" if v is None or pd.isna(v) else f"{v:+,.2f}"


# ------------------------------------------------------------------ live section
@st.fragment(run_every="5s")
def live_section():
    conn = q.connect(DB_PATH)
    if conn is None:
        st.info(f"No database yet at {DB_PATH}. Run the bot or a backtest first.")
        return
    try:
        hb, hb_ts = q.state(conn, "heartbeat")
        acct, _ = q.state(conn, "account")
        alloc, _ = q.state(conn, "allocation")
        run, _ = q.state(conn, "run")
        age = q.heartbeat_age_seconds(conn)

        if age is None:
            status = "never run"
        elif hb and hb.get("waiting_for"):
            status = "waiting for open"
        elif age < 60:
            status = "running"
        else:
            status = f"stale ({age / 60:.0f} min)"

        c1, c2, c3, c4, c5 = st.columns(5)
        c1.metric("Equity", money(acct["equity"]) if acct else "—")
        c2.metric("Cash", money(acct["cash"]) if acct else "—")
        c3.metric("Today's allocation", money(alloc) if alloc else money(settings.capital.base_allocation))
        c4.metric("Bot", status, help=f"last heartbeat {hb_ts.astimezone(ET):%H:%M:%S} ET" if hb_ts else None)
        c5.metric("Universe", hb.get("universe", "—") if hb else "—", help="symbols being watched" if hb else None)

        st.subheader("Open positions")
        pos = q.positions(conn)
        if pos.empty:
            st.caption("None.")
        else:
            view = pos[
                [
                    "symbol",
                    "qty",
                    "entry_price",
                    "last_price",
                    "peak_price",
                    "exit_trigger",
                    "unrealized",
                    "unrealized_pct",
                    "from_peak_pct",
                    "held_min",
                ]
            ].copy()
            st.dataframe(
                view,
                hide_index=True,
                width="stretch",
                column_config={
                    "symbol": "Symbol",
                    "qty": st.column_config.NumberColumn("Qty", format="%d"),
                    "entry_price": st.column_config.NumberColumn("Entry", format="$%.2f"),
                    "last_price": st.column_config.NumberColumn("Current", format="$%.2f"),
                    "peak_price": st.column_config.NumberColumn("Peak", format="$%.2f"),
                    "exit_trigger": st.column_config.NumberColumn(
                        "Sell if ≤", format="$%.2f", help="Wave-exit trigger. Blank = gain floor not reached yet"
                    ),
                    "unrealized": st.column_config.NumberColumn("P/L", format="$%.2f"),
                    "unrealized_pct": st.column_config.NumberColumn("P/L %", format="%.2f%%"),
                    "from_peak_pct": st.column_config.NumberColumn("From peak", format="%.2f%%"),
                    "held_min": st.column_config.NumberColumn("Held (min)", format="%.0f"),
                },
            )
            st.caption(f"Unrealized total: {signed(pos['unrealized'].sum())}")

        today_et = datetime.now(ET).replace(hour=0, minute=0, second=0, microsecond=0)
        since = today_et.astimezone(timezone.utc).isoformat()
        st.subheader("Today's closed trades")
        tr = q.trades(conn, "live", since=since)
        if tr.empty:
            st.caption("None yet.")
        else:
            realized = tr["pnl"].sum()
            wins = int((tr["pnl"] > 0).sum())
            st.caption(f"Realized: {signed(realized)} on {len(tr)} trades, {wins} winners.")
            view = tr[
                [
                    "symbol",
                    "qty",
                    "entry_time",
                    "entry_price",
                    "exit_time",
                    "exit_price",
                    "peak_price",
                    "pnl",
                    "pnl_pct",
                    "exit_reason",
                    "held_min",
                ]
            ].copy()
            view["entry_time"] = view["entry_time"].dt.tz_convert(ET).dt.strftime("%H:%M")
            view["exit_time"] = view["exit_time"].dt.tz_convert(ET).dt.strftime("%H:%M")
            st.dataframe(
                view,
                hide_index=True,
                width="stretch",
                column_config={
                    "symbol": "Symbol",
                    "qty": st.column_config.NumberColumn("Qty", format="%d"),
                    "entry_time": "In",
                    "exit_time": "Out",
                    "entry_price": st.column_config.NumberColumn("Entry", format="$%.2f"),
                    "exit_price": st.column_config.NumberColumn("Exit", format="$%.2f"),
                    "peak_price": st.column_config.NumberColumn("Peak", format="$%.2f"),
                    "pnl": st.column_config.NumberColumn("P/L", format="$%.2f"),
                    "pnl_pct": st.column_config.NumberColumn("P/L %", format="%.2f%%"),
                    "exit_reason": "Why",
                    "held_min": st.column_config.NumberColumn("Held (min)", format="%.0f"),
                },
            )

        with st.expander("Today's orders"):
            od = q.orders_today(conn, since)
            st.dataframe(od, hide_index=True, width="stretch") if not od.empty else st.caption("None.")
    finally:
        conn.close()


def ledger_section():
    conn = q.connect(DB_PATH)
    if conn is None:
        return
    try:
        st.subheader("Daily ledger")
        led = q.ledger(conn, "live")
        if led.empty:
            st.caption("No completed trading days yet.")
            return
        c1, c2 = st.columns(2)
        with c1:
            st.caption("Realized P/L per day")
            st.plotly_chart(pnl_bars(led, "date", "realized_pnl"), width="stretch")
        with c2:
            st.caption("Cumulative realized P/L")
            st.plotly_chart(line_chart(led, "date", "cumulative_realized", "$"), width="stretch")
        view = led[
            [
                "date",
                "trades",
                "wins",
                "losses",
                "realized_pnl",
                "unrealized_pnl",
                "cumulative_realized",
                "allocation",
                "next_allocation",
                "equity_close",
            ]
        ]
        st.dataframe(
            view,
            hide_index=True,
            width="stretch",
            column_config={
                "realized_pnl": st.column_config.NumberColumn("Realized", format="$%.2f"),
                "unrealized_pnl": st.column_config.NumberColumn("Unrealized", format="$%.2f"),
                "cumulative_realized": st.column_config.NumberColumn("Cumulative", format="$%.2f"),
                "allocation": st.column_config.NumberColumn("Allocation", format="$%.0f"),
                "next_allocation": st.column_config.NumberColumn("Next allocation", format="$%.0f"),
                "equity_close": st.column_config.NumberColumn("Equity at close", format="$%.2f"),
            },
        )
    finally:
        conn.close()


def backtest_section():
    conn = q.connect(DB_PATH)
    if conn is None:
        return
    try:
        runs = q.backtest_runs(conn)
        if runs.empty:
            st.caption("No backtests yet. Run `uv run python scripts/run_backtest.py --start ... --end ...`.")
            return
        labels = [
            f"{r.start_date} → {r.end_date} · {r.feed} · {len(r.universe)} symbols · {r.id}" for r in runs.itertuples()
        ]
        idx = st.selectbox("Run", range(len(labels)), format_func=lambda i: labels[i])
        run = runs.iloc[idx]
        s = run["summary"] or {}
        c1, c2, c3, c4, c5, c6 = st.columns(6)
        c1.metric("Trades", s.get("trades", "—"))
        c2.metric("Win rate", f"{s['win_rate']:.0%}" if s.get("win_rate") is not None else "—")
        c3.metric("Net P/L", signed(s.get("total_pnl")))
        c4.metric("Profit factor", f"{s['profit_factor']:.2f}" if s.get("profit_factor") else "—")
        c5.metric("Max drawdown", money(s.get("max_drawdown")))
        c6.metric("Avg hold", f"{s['avg_hold_minutes']:.0f} min" if s.get("avg_hold_minutes") else "—")
        if s.get("exit_reasons"):
            st.caption("Exits: " + ", ".join(f"{k} {v}" for k, v in s["exit_reasons"].items()))

        ec = q.equity_curve(conn, run["id"])
        if not ec.empty:
            st.caption("Equity curve")
            st.plotly_chart(line_chart(ec, "ts", "equity", "$"), width="stretch")
        led = q.ledger(conn, run["id"])
        if not led.empty:
            st.caption("Realized P/L per day")
            st.plotly_chart(pnl_bars(led, "date", "realized_pnl"), width="stretch")
        tr = q.trades(conn, "backtest", run_id=run["id"])
        if not tr.empty:
            view = tr[
                [
                    "symbol",
                    "qty",
                    "entry_time",
                    "entry_price",
                    "exit_time",
                    "exit_price",
                    "peak_price",
                    "pnl",
                    "pnl_pct",
                    "exit_reason",
                    "held_min",
                ]
            ].copy()
            for c in ("entry_time", "exit_time"):
                view[c] = view[c].dt.tz_convert(ET).dt.strftime("%m-%d %H:%M")
            st.dataframe(
                view,
                hide_index=True,
                width="stretch",
                column_config={
                    "entry_price": st.column_config.NumberColumn("Entry", format="$%.2f"),
                    "exit_price": st.column_config.NumberColumn("Exit", format="$%.2f"),
                    "peak_price": st.column_config.NumberColumn("Peak", format="$%.2f"),
                    "pnl": st.column_config.NumberColumn("P/L", format="$%.2f"),
                    "pnl_pct": st.column_config.NumberColumn("P/L %", format="%.2f%%"),
                    "held_min": st.column_config.NumberColumn("Held (min)", format="%.0f"),
                },
            )
        with st.expander("Parameters used"):
            st.json(run["params_json"], expanded=False)
    finally:
        conn.close()


st.title("Ride The Wave")
st.caption(
    f"Paper trading · {settings.universe.source} universe · {settings.alpaca.data_feed.upper()} feed · "
    f"{datetime.now(ET):%a %b %d, %H:%M} ET"
)


def reports_section():
    from pathlib import Path

    root = Path(settings.operator.report_dir)
    root = root if root.is_absolute() else DB_PATH.parent.parent / root
    if not root.exists():
        st.caption("No reports yet. They are written by scripts/report.py on the operator schedule.")
        return
    days = sorted([d for d in root.iterdir() if d.is_dir()], reverse=True)
    if not days:
        st.caption("No reports yet.")
        return
    day = st.selectbox("Day", [d.name for d in days])
    files = sorted((root / day).glob("*.md"), reverse=True)
    pick = st.selectbox("Report", [f.name for f in files])
    st.markdown((root / day / pick).read_text())


tab_live, tab_reports, tab_ledger, tab_bt = st.tabs(["Live", "Reports", "Ledger", "Backtests"])
with tab_live:
    live_section()
with tab_reports:
    reports_section()
with tab_ledger:
    ledger_section()
with tab_bt:
    backtest_section()
