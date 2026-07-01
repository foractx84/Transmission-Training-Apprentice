"""Program Analytics page — cohort-level analytics and insights."""

import logging
import sys
from pathlib import Path
from html import escape

sys.path.insert(0, str(Path(__file__).parent.parent))

import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
import streamlit as st

from app.components.navigation import require_auth, render_sidebar
from app.core.rbac import has_role, ROLE_ADMIN, ROLE_SUPERVISOR, ROLE_AUDITOR
from app.services.analytics_service import load_program_analytics, load_analytics_trend
from app.utils.formatters import format_date
from app.utils.org_groups import (
    BUSINESS_GROUPS,
    UNMAPPED,
    classify_business_group,
)

logger = logging.getLogger(__name__)


# ── Styles ────────────────────────────────────────────────────────────────────


def _inject_styles() -> None:
    st.markdown(
        """
        <style>
        .kpi-card {
            background: #1e2130;
            border-radius: 12px;
            padding: 1.2rem 1.5rem;
            text-align: center;
            margin-bottom: 0.5rem;
        }
        .kpi-label { font-size: 0.8rem; color: #a0aec0; margin-bottom: 0.3rem; }
        .kpi-value { font-size: 1.8rem; font-weight: 700; color: #ffffff; }
        .kpi-alert { border: 1px solid #fc8181; }

        .section-header {
            font-size: 1.1rem;
            font-weight: 700;
            color: #e2e8f0;
            margin: 1.5rem 0 0.25rem 0;
        }
        .placeholder-box {
            background: #1e2130;
            border-radius: 12px;
            padding: 2rem;
            text-align: center;
            color: #4a5568;
            border: 1px dashed #2d3748;
            min-height: 180px;
            display: flex;
            align-items: center;
            justify-content: center;
            margin-bottom: 1rem;
        }
        .form-section {
            background: #1e2130;
            border-radius: 12px;
            padding: 1.5rem;
            margin-bottom: 1rem;
        }
        .form-field-label {
            font-size: 0.8rem;
            color: #a0aec0;
            margin-bottom: 0.1rem;
        }
        .form-field-value {
            font-size: 0.95rem;
            color: #e2e8f0;
            margin-bottom: 0.75rem;
            font-weight: 500;
        }
        .result-pass {
            background: #276749;
            color: #f0fff4;
            padding: 0.3rem 0.75rem;
            border-radius: 6px;
            display: inline-block;
            font-weight: 700;
        }
        .result-fail {
            background: #9b2c2c;
            color: #fff5f5;
            padding: 0.3rem 0.75rem;
            border-radius: 6px;
            display: inline-block;
            font-weight: 700;
        }
        .section-divider { border-top: 1px solid #2d3748; margin: 1rem 0; }
        .st-key-kpi_card_alerts,
        .st-key-kpi_card_fails,
        .st-key-kpi_card_delays {
            margin-top: -6.4rem;
            position: relative;
            z-index: 5;
        }
        .st-key-kpi_card_alerts button,
        .st-key-kpi_card_fails button,
        .st-key-kpi_card_delays button {
            height: 5.4rem;
            opacity: 0;
            cursor: pointer;
        }
        .kpi-card { cursor: pointer; transition: border 0.15s ease; }
        .kpi-card:hover { border: 1px solid #63b3ed; }
        </style>
        """,
        unsafe_allow_html=True,
    )


# ── KPI Cards ─────────────────────────────────────────────────────────────────


def _kpi_card(label: str, value: str, alert: bool = False) -> None:
    alert_class = "kpi-alert" if alert else ""
    st.markdown(
        f"""
        <div class="kpi-card {alert_class}">
            <div class="kpi-label">{escape(label)}</div>
            <div class="kpi-value">{escape(str(value))}</div>
        </div>
        """,
        unsafe_allow_html=True,
    )


def _render_kpis(df: pd.DataFrame) -> None:
    c1, c2, c3, c4, c5 = st.columns(5)

    clickable = [
        (c1, "Program Alerts", "coming_due", "alerts"),
        (c2, "Program Fails", "failed_courses", "fails"),
        (c3, "Active Delays", "delayed_courses", "delays"),
    ]
    for col, label, value_col, drill_key in clickable:
        total = int(df[value_col].sum()) if not df.empty else 0
        with col:
            _kpi_card(label, str(total), alert=total > 0)
            if st.button(
                f"Open {label}", key=f"kpi_card_{drill_key}", use_container_width=True
            ):
                # Toggle: click the same card again to close.
                st.session_state.kpi_drill = (
                    None
                    if st.session_state.get("kpi_drill") == drill_key
                    else drill_key
                )

    with c4:
        avg = round(df["completion_pct"].mean(), 1) if not df.empty else 0.0
        _kpi_card("Overall Completion", f"{avg}%")
    with c5:
        _kpi_card("Financial Impact", "000")

    _render_kpi_drilldown(df)


def _render_kpi_drilldown(df: pd.DataFrame) -> None:
    """4.1–4.3 — show who/what contributes to the clicked KPI card."""
    drill = st.session_state.get("kpi_drill")
    if not drill:
        return

    if drill == "alerts":
        title = "🔔 Program Alerts — coming due"
        caption = "Included because a recert or assignment is coming due."
        sub = df[df["coming_due"] > 0]
        cols = {
            "name": "Apprentice",
            "supervisor_name": "Supervisor",
            "coming_due": "Coming Due",
            "expected_completion": "Expected Completion",
            "status": "Status",
        }
    elif drill == "fails":
        title = "❌ Program Fails"
        caption = "Apprentices with one or more failed courses."
        sub = df[df["failed_courses"] > 0]
        cols = {
            "name": "Apprentice",
            "supervisor_name": "Supervisor",
            "failed_courses": "Failed Courses",
            "fail_rate_pct": "Fail Rate %",
            "status": "Status",
        }
    else:  # delays
        title = "⏳ Active Delays"
        caption = "Apprentices with one or more delayed tasks."
        sub = df[df["delayed_courses"] > 0]
        cols = {
            "name": "Apprentice",
            "supervisor_name": "Supervisor",
            "delayed_courses": "Delayed Tasks",
            "expected_completion": "Expected Completion",
            "status": "Status",
        }

    st.markdown('<div class="section-divider"></div>', unsafe_allow_html=True)
    st.markdown(f"#### {title}")
    st.caption(caption)

    if sub.empty:
        st.success("Nothing to show — count is zero for the current filters.")
        return

    table = sub[list(cols.keys())].copy()
    if "expected_completion" in table.columns:
        table["expected_completion"] = table["expected_completion"].apply(format_date)
    table.columns = list(cols.values())
    st.dataframe(table, use_container_width=True, hide_index=True)
    st.caption(f"{len(sub)} apprentice(s) contributing.")


# ── Plotly chart helper ───────────────────────────────────────────────────────


def _dark_layout(fig: go.Figure, height: int = 350) -> go.Figure:
    fig.update_layout(
        plot_bgcolor="#0e1117",
        paper_bgcolor="#0e1117",
        font_color="#e2e8f0",
        showlegend=False,
        coloraxis_showscale=False,
        margin=dict(l=0, r=0, t=40, b=0),
        height=height,
    )
    return fig


def _abbr(text: str) -> str:
    """Apprentice -> Appr., Supervisor -> Sup., etc."""
    return text.replace("Apprentices", "Appr.").replace("Apprentice", "Appr.")


# ── Section: Trend ────────────────────────────────────────────────────────────


def _render_trend(
    trend_data: list[dict],
    year_filter: str,
    quarter_filter: str,
) -> None:
    if not trend_data:
        st.info("No trend data available.")
        return

    trend_df = pd.DataFrame(trend_data)
    trend_df["month"] = pd.to_datetime(trend_df["month"], format="%Y-%m")

    if year_filter != "All":
        trend_df = trend_df[trend_df["month"].dt.year == int(year_filter)]
    if quarter_filter != "All":
        trend_df = trend_df[trend_df["month"].dt.quarter == int(quarter_filter[1])]

    if trend_df.empty:
        st.info("No trend data for selected period.")
        return

    fig = go.Figure()
    fig.add_trace(
        go.Scatter(
            x=trend_df["month"],
            y=trend_df["completions"],
            mode="lines+markers",
            name="Completions",
            line=dict(color="#63b3ed", width=2),
            marker=dict(size=6),
        )
    )
    fig.add_trace(
        go.Scatter(
            x=trend_df["month"],
            y=trend_df["failures"],
            mode="lines+markers",
            name="Failures",
            line=dict(color="#fc8181", width=2),
            marker=dict(size=6),
        )
    )
    fig.add_trace(
        go.Scatter(
            x=trend_df["month"],
            y=trend_df["delays"],
            mode="lines+markers",
            name="Delays",
            line=dict(color="#f6ad55", width=2),
            marker=dict(size=6),
        )
    )
    fig.update_layout(
        plot_bgcolor="#0e1117",
        paper_bgcolor="#0e1117",
        font_color="#e2e8f0",
        showlegend=True,
        legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="right", x=1),
        xaxis=dict(showgrid=False),
        yaxis=dict(showgrid=True, gridcolor="#2d3748"),
        margin=dict(l=0, r=0, t=10, b=0),
        hovermode="x unified",
        height=350,
    )
    st.plotly_chart(fig, use_container_width=True)


# ── Section: Pass/Fail donut ──────────────────────────────────────────────────


def _render_pass_fail(df: pd.DataFrame) -> None:
    if df.empty:
        return

    fig = go.Figure(
        go.Pie(
            labels=["Completed", "Failed", "Delayed", "Coming Due"],
            values=[
                int(df["completed_courses"].sum()),
                int(df["failed_courses"].sum()),
                int(df["delayed_courses"].sum()),
                int(df["coming_due"].sum()),
            ],
            hole=0.5,
            marker_colors=["#68d391", "#fc8181", "#f6ad55", "#63b3ed"],
        )
    )
    fig.update_layout(
        plot_bgcolor="#0e1117",
        paper_bgcolor="#0e1117",
        font_color="#e2e8f0",
        showlegend=True,
        legend=dict(orientation="h", yanchor="bottom", y=-0.2),
        margin=dict(l=0, r=0, t=10, b=40),
        height=350,
    )
    st.plotly_chart(fig, use_container_width=True)


# ── Section: Completion by Apprentice Year ──────────────────────────────────────────────


def _render_completion_by_year(df: pd.DataFrame) -> None:
    if df.empty:
        st.info("No data.")
        return
    if "apprentice_year_label" not in df.columns:
        st.warning(
            "Apprentice-year columns not loaded — the data is cached. "
            'Clear the cache (press "C", or ⋮ → Clear cache) and rerun.'
        )
        return

    no_year_mask = df["apprentice_year"].isna() | df["apprentice_year_label"].fillna(
        ""
    ).str.strip().isin(["", "Unknown"])
    no_year_count = int(no_year_mask.sum())

    year_df = (
        df.dropna(subset=["apprentice_year"])  # drop Unknown/null years
        .groupby(["apprentice_year", "apprentice_year_label"], as_index=False)[
            "completion_pct"
        ]
        .mean()
        .sort_values("apprentice_year")  # 1st → 4th order
        .rename(
            columns={
                "completion_pct": "Avg Completion %",
                "apprentice_year_label": "Year",
            }
        )
    )
    if year_df.empty:
        st.info("No apprentice-year values for the current filters.")
        return

    fig = px.bar(
        year_df,
        x="Year",
        y="Avg Completion %",  # vertical columns
        color="Avg Completion %",
        color_continuous_scale="Blues",
        range_y=[0, 100],
        text=year_df["Avg Completion %"].apply(lambda v: f"{v:.1f}%"),
    )
    fig.update_traces(textposition="outside")
    fig.update_xaxes(title_text="", tickangle=0)
    st.plotly_chart(_dark_layout(fig), use_container_width=True)

    if no_year_count:
        st.caption(
            f"⚠️ {no_year_count} apprentice(s) have no assigned year (excluded above)."
        )


# ── Helper: row-level Division/BU fallback ──────────────────────────────────


def _division_or_bu(df: pd.DataFrame) -> pd.Series:
    """Per-row Division/BU label — uses division when present, else bu.
    Empty/whitespace strings are treated as missing."""
    division = df["division"].replace(r"^\s*$", pd.NA, regex=True)
    bu = df["bu"].replace(r"^\s*$", pd.NA, regex=True)
    return division.fillna(bu)


# ── Section: Completion by Division/BU ───────────────────────────────────────


def _render_completion_by_division(df: pd.DataFrame) -> None:
    if df.empty:
        st.info("No data.")
        return

    div_df = df.copy()
    div_df["Division/BU"] = _division_or_bu(div_df)
    div_df = (
        div_df.dropna(subset=["Division/BU"])
        .groupby("Division/BU")["completion_pct"]
        .mean()
        .reset_index()
        .rename(columns={"completion_pct": "Avg Completion %"})
        .sort_values("Avg Completion %", ascending=True)
    )
    fig = px.bar(
        div_df,
        x="Avg Completion %",
        y="Division/BU",
        orientation="h",
        color="Avg Completion %",
        color_continuous_scale="Teal",
        range_x=[0, 100],
        text=div_df["Avg Completion %"].apply(lambda v: f"{v:.1f}%"),
    )
    fig.update_traces(textposition="outside")
    st.plotly_chart(_dark_layout(fig), use_container_width=True)


# ── Section: Completion by Supervisor — paginated table ───────────────────────


def _render_supervisor_table(df: pd.DataFrame) -> str | None:
    st.markdown("##### Supervisor Summary")
    if df.empty:
        st.info("No data.")
        return None

    sup_df = (
        df.groupby("supervisor_name")
        .agg(
            avg_completion=("completion_pct", "mean"),
            apprentice_count=("id", "count"),
            at_risk=("status", lambda x: (x == "At Risk").sum()),
            delayed=("delayed_courses", "sum"),
        )
        .reset_index()
        .rename(columns={"supervisor_name": "Supervisor"})
        .sort_values("avg_completion", ascending=False)
    )
    sup_df["avg_completion"] = sup_df["avg_completion"].apply(lambda v: f"{v:.1f}%")
    sup_df["at_risk"] = sup_df["at_risk"].astype(int)
    sup_df["delayed"] = sup_df["delayed"].astype(int)
    sup_df.columns = [
        "Supervisor",
        "Avg Completion %",
        _abbr("# Apprentices"),
        "At Risk",
        "Delayed",
    ]

    # Paginate — 10 rows per page
    page_size = 10
    total_pages = max(1, -(-len(sup_df) // page_size))  # ceil division
    page = st.number_input(
        "Page", min_value=1, max_value=total_pages, value=1, step=1, key="sup_page"
    )
    start = (page - 1) * page_size
    page_slice = sup_df.iloc[start : start + page_size]
    event = st.dataframe(
        page_slice,
        use_container_width=True,
        hide_index=True,
        on_select="rerun",
        selection_mode="single-row",
        key="sup_select",
    )
    st.caption(
        f"Showing {start + 1}–{min(start + page_size, len(sup_df))} of {len(sup_df)} supervisors"
    )

    selected_rows = event.selection.rows if event and event.selection else []
    if selected_rows:
        return str(page_slice.iloc[selected_rows[0]]["Supervisor"])
    return None


# ── Section: At Risk — paginated table ───────────────────────────────────────


def _render_at_risk_table(
    df: pd.DataFrame, selected_supervisor: str | None = None
) -> None:
    st.markdown("##### Individual Apprentice Details")

    at_risk = df[df["status"] == "At Risk"]
    if selected_supervisor:
        at_risk = at_risk[at_risk["supervisor_name"] == selected_supervisor]
    at_risk = at_risk.sort_values("failed_courses", ascending=False)

    if at_risk.empty:
        if selected_supervisor:
            st.success(
                f"✅ No at-risk apprentices for {escape(selected_supervisor)}."
            )
        else:
            st.success("✅ No at-risk apprentices.")
        return

    display = at_risk[
        [
            "name",
            "level",
            "supervisor_name",
            "division",
            "completion_pct",
            "failed_courses",
            "delayed_courses",
        ]
    ].copy()
    display["completion_pct"] = display["completion_pct"].apply(lambda v: f"{v:.1f}%")
    display["failed_courses"] = display["failed_courses"].astype(int)
    display["delayed_courses"] = display["delayed_courses"].astype(int)
    display.columns = [
        "Name",
        "Level",
        "Supervisor",
        "Division",
        "Completion %",
        "Failed",
        "Delayed",
    ]

    # Paginate — 10 rows per page
    page_size = 10
    total_pages = max(1, -(-len(display) // page_size))
    page = st.number_input(
        "Page",
        min_value=1,
        max_value=total_pages,
        value=1,
        step=1,
        key=f"risk_page_{selected_supervisor or 'all'}",
    )
    start = (page - 1) * page_size
    st.dataframe(
        display.iloc[start : start + page_size],
        use_container_width=True,
        hide_index=True,
    )
    base_caption = (
        f"Showing {start + 1}–{min(start + page_size, len(display))} "
        f"of {len(display)} at-risk apprentices"
    )
    if selected_supervisor:
        base_caption += (
            f" · 🔗 filtered to {escape(selected_supervisor)} "
            "(click the same supervisor row again to clear)"
        )
    st.caption(base_caption)


# ── Section: Financial Analytics (Placeholder) ────────────────────────────────


def _render_financial_analytics() -> None:
    st.markdown(
        '<div class="section-header">💰 Financial Analytics</div>',
        unsafe_allow_html=True,
    )
    st.markdown("---")
    st.markdown(
        """
        <div class="placeholder-box">
            <div>
                <div style="font-size:2rem">💰</div>
                <div style="margin-top:0.5rem; color:#718096">
                    Financial Analytics — Coming Soon<br>
                    <small>Pending data source confirmation</small>
                </div>
            </div>
        </div>
        """,
        unsafe_allow_html=True,
    )


# ── Section: Detailed Table ───────────────────────────────────────────────────


def _render_table(df: pd.DataFrame) -> None:
    st.markdown(
        '<div class="section-header">📋 Detailed Breakdown</div>',
        unsafe_allow_html=True,
    )
    st.markdown("---")

    if df.empty:
        st.info("No records found.")
        return

    status_icons = {
        "On Track": "🟢 On Track",
        "Delayed": "🟡 Delayed",
        "At Risk": "🔴 At Risk",
        "Completed": "🔵 Completed",
    }

    display = df[
        [  # ← fixed: [[ not [{
            "name",
            "level",
            "supervisor_name",
            "division",
            "completion_pct",
            "fail_rate_pct",
            "status",
            "delayed_courses",
            "expected_completion",
        ]
    ].copy()

    display["status"] = display["status"].map(status_icons).fillna(display["status"])
    display["completion_pct"] = display["completion_pct"].apply(lambda x: f"{x:.1f}%")
    display["fail_rate_pct"] = display["fail_rate_pct"].apply(lambda x: f"{x:.1f}%")
    display["expected_completion"] = display["expected_completion"].apply(format_date)

    display.columns = [
        "Name",
        "Level",
        "Supervisor",
        "Division",
        "Completion %",
        "Fail Rate %",
        "Status",
        "Delayed Courses",
        "Expected Completion",
    ]
    st.dataframe(display, use_container_width=True, hide_index=True)


# ── Page entry point ──────────────────────────────────────────────────────────


def main() -> None:
    auth = require_auth()
    user_info = render_sidebar(auth)

    if not any(has_role(auth, r) for r in [ROLE_SUPERVISOR, ROLE_ADMIN, ROLE_AUDITOR]):
        st.error(
            "🚫 Access Denied — This page is restricted to supervisors, admins, and auditors."
        )
        st.stop()

    _inject_styles()
    st.title("Program Analytics")
    st.markdown("---")

    is_supervisor_only = (
        has_role(auth, ROLE_SUPERVISOR)
        and not has_role(auth, ROLE_ADMIN)
        and not has_role(auth, ROLE_AUDITOR)
    )
    supervisor_name_filter: str | None = None
    if is_supervisor_only:
        supervisor_name_filter = (user_info.get("displayName") or "").strip() or None
        if not supervisor_name_filter:
            st.error(
                "🚫 Cannot resolve your supervisor identity from Azure AD. Contact admin."
            )
            st.stop()

    # ── Sidebar Filters ───────────────────────────────────────────────────────
    st.sidebar.markdown("### Filters")

    with st.spinner("Loading analytics…"):
        all_data = load_program_analytics(supervisor_name_filter)

    df = pd.DataFrame(all_data)

    if df.empty:
        st.warning("No analytics data available.")
        return

    df["business_group"] = df["org_group"].map(classify_business_group)

    years = ["All"] + sorted(
        df["expected_completion"]
        .dropna()
        .apply(lambda d: str(d.year) if hasattr(d, "year") else None)
        .dropna()
        .unique()
        .tolist(),
        reverse=True,
    )
    selected_year = st.sidebar.selectbox("Year", years)
    selected_quarter = st.sidebar.selectbox("Quarter", ["All", "Q1", "Q2", "Q3", "Q4"])

    st.sidebar.markdown("**Date Range (Expected Completion)**")
    min_date = df["expected_completion"].dropna().min()
    max_date = df["expected_completion"].dropna().max()
    if pd.notna(min_date) and pd.notna(max_date):
        date_from = st.sidebar.date_input(
            "From", value=min_date, min_value=min_date, max_value=max_date
        )
        date_to = st.sidebar.date_input(
            "To", value=max_date, min_value=min_date, max_value=max_date
        )
    else:
        date_from = date_to = None

    selected_org = st.sidebar.selectbox("Org Group", ["All Electric"] + BUSINESS_GROUPS)

    unmapped = (
        df.loc[df["business_group"] == UNMAPPED, "org_group"]
        .replace("", pd.NA)
        .dropna()
        .value_counts()
    )
    if not unmapped.empty:
        with st.sidebar.expander(
            f"⚙ Org mapping — {len(unmapped)} unmapped", expanded=False
        ):
            st.caption("Add keywords for these in app/utils/org_groups.py:")
            for cost_center, n in unmapped.items():
                st.caption(f"• {cost_center} ({n})")

    levels = ["All"] + sorted(df["level"].dropna().unique().tolist())
    selected_level = st.sidebar.selectbox("Level", levels)

    div_bu_series = _division_or_bu(df)
    divs = ["All"] + sorted(div_bu_series.dropna().unique().tolist())
    selected_div = st.sidebar.selectbox("Division / BU", divs)
    selected_status = st.sidebar.selectbox(
        "Status", ["All", "On Track", "Delayed", "At Risk", "Completed"]
    )

    if not is_supervisor_only:
        supervisors = ["All"] + sorted(df["supervisor_name"].dropna().unique().tolist())
        selected_supervisor = st.sidebar.selectbox("Supervisor", supervisors)
    else:
        selected_supervisor = "All"

    # ── Apply Filters ─────────────────────────────────────────────────────────
    filtered = df.copy()
    if selected_org != "All Electric":
        filtered = filtered[filtered["business_group"] == selected_org]
    if selected_level != "All":
        filtered = filtered[filtered["level"] == selected_level]
    if selected_div != "All":
        filtered = filtered[_division_or_bu(filtered) == selected_div]
    if selected_status != "All":
        filtered = filtered[filtered["status"] == selected_status]
    if selected_supervisor != "All":
        filtered = filtered[filtered["supervisor_name"] == selected_supervisor]
    if selected_year != "All":
        ec = pd.to_datetime(filtered["expected_completion"], errors="coerce")
        filtered = filtered[ec.dt.year.eq(int(selected_year)).fillna(False)]
    if selected_quarter != "All":
        quarter_number = int(selected_quarter[1:])
        ec = pd.to_datetime(filtered["expected_completion"], errors="coerce")
        filtered = filtered[ec.dt.quarter.eq(quarter_number).fillna(False)]
    if date_from and date_to:
        filtered = filtered[
            filtered["expected_completion"].apply(
                lambda d: date_from <= d <= date_to if d else False
            )
        ]

    # ═════════════════════════════════════════════════════════════════════════
    # 1-COLUMN LAYOUT — top to bottom
    # ═════════════════════════════════════════════════════════════════════════

    # 1. KPI Row
    _render_kpis(filtered)
    st.markdown("<br>", unsafe_allow_html=True)

    # 2. Trend + Pass/Fail — side by side ─────────────────────────────────────
    # Scope the trend to the same apprentices as the rest of the dashboard.
    filtered_emp_ids = tuple(
        sorted(filtered["id"].dropna().astype(str).unique().tolist())
    )
    trend_data = load_analytics_trend(
        supervisor_name_filter, employee_ids=filtered_emp_ids
    )

    st.markdown(
        '<div class="section-header">📈 Completion Trend Over Time &nbsp;&nbsp;|&nbsp;&nbsp; ✅ Course Pass / Fail Rates</div>',
        unsafe_allow_html=True,
    )
    st.markdown("---")
    col_trend, col_pf = st.columns([2, 1])
    with col_trend:
        _render_trend(trend_data, selected_year, selected_quarter)
    with col_pf:
        _render_pass_fail(filtered)

    # 3. Completion by Apprentice Year ───────────────────────────────────────────────────
    st.markdown(
        '<div class="section-header">🎓 Completion Rate by Apprentice Year</div>',
        unsafe_allow_html=True,
    )
    st.markdown("---")
    _render_completion_by_year(filtered)

    # 4. Completion by Division/BU ─────────────────────────────────────────────
    st.markdown(
        '<div class="section-header">🏢 Completion Rate by Division / BU</div>',
        unsafe_allow_html=True,
    )
    st.markdown("---")
    _render_completion_by_division(filtered)

    # 5. Supervisor + At Risk — side by side paginated tables ─────────────────
    st.markdown(
        '<div class="section-header">👤 Completion by Supervisor &nbsp;&nbsp;|&nbsp;&nbsp; 🔴 At Risk Apprentices</div>',
        unsafe_allow_html=True,
    )
    st.markdown("---")
    col_sup, col_risk = st.columns(2)
    with col_sup:
        selected_supervisor = _render_supervisor_table(filtered)
    with col_risk:
        _render_at_risk_table(filtered, selected_supervisor)

    # 6. Financial Analytics Placeholder ──────────────────────────────────────
    _render_financial_analytics()

    # 7. Detailed Breakdown Table ─────────────────────────────────────────────
    _render_table(filtered)


main()
