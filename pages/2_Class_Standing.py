"""Class Standing page — cohort-level progress overview."""

import sys
from datetime import date
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

import pandas as pd
import streamlit as st
from html import escape

from app.components.navigation import require_auth, render_sidebar
from app.services.analytics_service import (
    load_class_standing,
    load_delayed_tasks,
    load_alert_items,
)
from app.utils.formatters import format_date
from app.core.rbac import has_role, ROLE_ADMIN, ROLE_SUPERVISOR, ROLE_AUDITOR


# ── Styles ────────────────────────────────────────────────────────────────────


def _inject_styles() -> None:
    st.markdown(
        """
        <style>
        .metric-card {
            background: #1e2130;
            border: 1px solid #2d3748;
            border-radius: 12px;
            padding: 1.25rem 1rem;
            text-align: center;
            margin-bottom: 0.5rem;
            min-height: 148px;
            display: flex;
            flex-direction: column;
            align-items: center;
            justify-content: center;
        }
        .metric-label {
            font-size: 0.78rem;
            color: #a0aec0;
            text-transform: uppercase;
            letter-spacing: 0.04em;
            line-height: 1.25;
            min-height: 2.4em;
            display: flex;
            align-items: center;
            justify-content: center;
        }
        .metric-value {
            font-size: 1.9rem;
            font-weight: 700;
            color: #ffffff;
            line-height: 1.15;
            white-space: nowrap;
            margin-top: 0.35rem;
        }
        .metric-sub {
            font-size: 0.82rem;
            color: #63b3ed;
            margin-top: 0.45rem;
        }
        .st-key-delayed_drill_btn {
            margin-top: -9.75rem;
            position: relative;
            z-index: 5;
        }
        .st-key-delayed_drill_btn button {
            height: 9.25rem;
            opacity: 0;
            cursor: pointer;
        }
        .metric-card.clickable { cursor: pointer; transition: border 0.15s ease; }
        .metric-card.clickable:hover { border-color: #63b3ed; }
        </style>
        """,
        unsafe_allow_html=True,
    )


# ── Metric cards ──────────────────────────────────────────────────────────────


def _metric_card(
    label: str, value: str, sub: str | None = None, clickable: bool = False
) -> None:
    sub_html = (
        f'<div class="metric-sub">{escape(str(sub))}</div>' if sub else ""
    )
    card_class = "metric-card clickable" if clickable else "metric-card"
    st.markdown(
        f"""
        <div class="{card_class}">
            <div class="metric-label">{escape(str(label))}</div>
            <div class="metric-value">{escape(str(value))}</div>
            {sub_html}
        </div>
        """,
        unsafe_allow_html=True,
    )

def _next_journeyman_completion(df: pd.DataFrame) -> tuple[date | None, int]:
    """Find the next month a group of apprentices is expected to complete.

    Each apprentice's `expected_completion` is their final-course date (a
    per-apprentice MAX from the query). We bucket those by month, pick the
    earliest upcoming month (falling back to the earliest overall if every
    date is in the past), and count how many apprentices land in it.
    """
    valid = pd.to_datetime(df["expected_completion"], errors="coerce").dropna()
    if valid.empty:
        return None, 0

    months = valid.dt.to_period("M")
    this_month = pd.Timestamp(date.today()).to_period("M")
    upcoming = months[months >= this_month]
    target = upcoming.min() if not upcoming.empty else months.min()

    count = int((months == target).sum())
    return target.to_timestamp().date(), count

def _render_metrics(df: pd.DataFrame) -> None:
    total = len(df)
    delayed = int((df["delayed_tasks"] > 0).sum())
    # Program Alerts = distinct apprentices who need attention: at least one
    # late (is_delayed) OR failed (is_failed) task. Excludes approaching/upcoming
    # (is_coming_due), which the old program_alerts sum included.
    alerts = int(((df["delayed_tasks"] > 0) | (df["failed_tasks"] > 0)).sum())
    next_month, completing = _next_journeyman_completion(df)

    c1, c2, c3, c4 = st.columns(4)
    with c1:
        _metric_card("Overall Standing", str(total))
    with c2:
        if next_month:
            _metric_card(
                "Next Journeyman Completion",
                format_date(next_month, "%b %Y"),
                sub=f"{completing} apprentice{'s' if completing != 1 else ''}",
            )
        else:
            _metric_card("Next Journeyman Completion", "N/A")
    with c3:
        _metric_card("Delayed Apprentices", str(delayed), clickable=True)
        if st.button(
            "Open delayed tasks",
            key="delayed_drill_btn",
            use_container_width=True,
        ):
            st.session_state.delayed_drill = not st.session_state.get(
                "delayed_drill", False
            )
    with c4:
        _metric_card("Program Alerts", str(alerts))

    _render_delayed_drilldown(df)

def _render_delayed_drilldown(df: pd.DataFrame) -> None:
    """Show who is delayed and exactly what they are delayed on.
    """
    if not st.session_state.get("delayed_drill"):
        return

    st.markdown("---")
    st.markdown("#### 🟡 Delayed Tasks — who & what")
    st.caption("Apprentices with one or more delayed tasks, and the tasks they're delayed on.")

    detail = load_delayed_tasks()
    if not detail.empty:
        detail = detail[detail["apprentice_id"].isin(set(df["id"]))]

    if detail.empty:
        st.success("✅ No delayed tasks for the current filters.")
        return

    table = detail[
        ["name", "level", "supervisor_name", "task", "status", "expected_completion_date"]
    ].copy()
    table["expected_completion_date"] = table["expected_completion_date"].apply(format_date)
    table.columns = [
        "Apprentice",
        "Level",
        "Supervisor",
        "Delayed Task",
        "Status",
        "Expected Completion",
    ]

    st.dataframe(table, use_container_width=True, hide_index=True)
    st.caption(
        f"{detail['apprentice_id'].nunique()} apprentice(s), {len(detail)} delayed task(s)."
    )

# ── Left column ───────────────────────────────────────────────────────────────


def _render_apprenticeship_level(df: pd.DataFrame) -> None:
    st.markdown("#### Apprenticeship Level")
    st.caption("List of enrolled students and key details")
    st.markdown("---")

    if df.empty:
        st.info("No apprentices found.")
        return

    level_summary = (
        df.groupby("level")
        .agg(
            count=("id", "count"),
            avg_pct=("completion_pct", "mean"),
            delayed=("delayed_tasks", "sum"),
        )
        .reset_index()
        .sort_values("level")
    )

    for _, row in level_summary.iterrows():
        avg_pct = row["avg_pct"]
        pct = round(float(avg_pct), 1) if pd.notna(avg_pct) else 0.0  # NaN-safe
        pct_clamped = min(max(pct / 100, 0.0), 1.0)  # ← clamp to [0.0, 1.0]
        st.markdown(f"**{row['level']}** — {int(row['count'])} apprentices")
        st.progress(pct_clamped, text=f"{pct}% avg completion")
        if row["delayed"] > 0:
            st.caption(f"⚠️ {int(row['delayed'])} delayed tasks")
        st.markdown("<br>", unsafe_allow_html=True)


def _render_training_insights(df: pd.DataFrame) -> None:
    st.markdown("#### Training Insights")
    st.caption("High priority training summaries by status")
    st.markdown("---")

    if df.empty:
        st.info("No training data available.")
        return

    at_risk = (
        df[df["status"].isin(["At Risk", "Delayed"])]
        .sort_values("delayed_tasks", ascending=False)
        .head(5)
    )

    if at_risk.empty:
        st.success("✅ No at-risk apprentices.")
    else:
        for _, row in at_risk.iterrows():
            icon = "🔴" if row["status"] == "At Risk" else "🟡"
            st.markdown(
                f"{icon} **{row['name']}** — "
                f"{int(row['delayed_tasks'])} delayed, "
                f"{int(row['program_alerts'])} alerts"
            )


# ── Middle column ─────────────────────────────────────────────────────────────


def _render_training_summary(df: pd.DataFrame) -> None:
    st.markdown("#### Training Summary and Recommendations")
    st.caption("Detailed list of training and insights from training")
    st.markdown("---")

    if df.empty:
        st.info("No training records available.")
        return

    counts = df["status"].value_counts()
    on_track = int(counts.get("On Track", 0))
    delayed = int(counts.get("Delayed", 0))
    at_risk = int(counts.get("At Risk", 0))
    completed = int(counts.get("Completed", 0))

    c1, c2 = st.columns(2)
    with c1:
        st.metric("On Track", on_track)
        st.metric("Completed", completed)
    with c2:
        st.metric(
            "Delayed",
            delayed,
            delta=f"-{delayed}" if delayed else None,
            delta_color="inverse",
        )
        st.metric(
            "At Risk",
            at_risk,
            delta=f"-{at_risk}" if at_risk else None,
            delta_color="inverse",
        )

    st.markdown("<br>", unsafe_allow_html=True)
    st.markdown("**Recommendations**")

    if at_risk > 0:
        st.warning(f"🔴 {at_risk} apprentice(s) at risk — review failed courses.")
    if delayed > 0:
        st.warning(f"🟡 {delayed} apprentice(s) delayed — follow up with supervisors.")
    if completed > 0:
        st.success(f"🔵 {completed} apprentice(s) completed the program.")
    if on_track == len(df) and len(df) > 0:
        st.success("✅ All apprentices are on track.")


# ── Right column ──────────────────────────────────────────────────────────────


def _render_docs_alerts(df: pd.DataFrame) -> None:
    st.markdown("#### Documentation & Alerts")
    st.caption("Training documentation roadmap and alerts")
    st.markdown("---")
    st.caption(
        "*Forming program guardrails and following process through an auditable process*"
    )

    if df.empty:
        st.info("No alerts.")
        return

    items = load_alert_items()
    if not items.empty:
        items = items[items["apprentice_id"].isin(set(df["id"]))]

    if items.empty:
        st.success("✅ No program alerts.")
        return

    # Due date per item: recerts (Coming Due) use requal_date; others use the
    # expected completion date.
    due = items["expected_completion_date"]
    if "requal_date" in items.columns:
        due = items["requal_date"].where(
            items["category"].eq("Coming Due") & items["requal_date"].notna(),
            items["expected_completion_date"],
        )
    items = items.assign(due_date=due)

    cat_icon = {"Failed": "🔴", "Late": "⏳", "Coming Due": "🟡"}
    cat_word = {"Failed": "failed", "Late": "late", "Coming Due": "coming due"}
    cat_order = ["Failed", "Late", "Coming Due"]

    # Most items first so the worst cases surface at the top.
    totals = items.groupby("apprentice_id").size().sort_values(ascending=False)

    for aid in totals.index:
        person = items[items["apprentice_id"] == aid]
        name = person["name"].iloc[0]
        total = len(person)
        counts = person["category"].value_counts()

        with st.expander(f"⚠️ {name} — {total} total item(s)"):
            breakdown = "  ·  ".join(
                f"{cat_icon[c]} {int(counts[c])} {cat_word[c]}"
                for c in cat_order
                if c in counts
            )
            st.markdown(breakdown)
            st.caption(
                f"Level: {person['level'].iloc[0]}  ·  "
                f"Supervisor: {person['supervisor_name'].iloc[0]}"
            )

            table = person[["task", "category", "status", "due_date"]].copy()
            table["due_date"] = table["due_date"].apply(format_date)
            table["category"] = table["category"].map(
                lambda c: f"{cat_icon.get(c, '')} {c}"
            )
            table.columns = ["Course / Task", "Issue", "Status", "Due / Expected"]
            st.dataframe(table, use_container_width=True, hide_index=True)


# ── Roster table ──────────────────────────────────────────────────────────────


def _render_roster(df: pd.DataFrame) -> None:
    st.markdown("#### Apprentice Roster")
    st.markdown("---")

    if df.empty:
        st.info("No apprentices found for the selected filters.")
        return

    status_icons = {
        "On Track": "🟢 On Track",
        "Delayed": "🟡 Delayed",
        "At Risk": "🔴 At Risk",
        "Completed": "🔵 Completed",
    }

    display = df[
        [
            "name",
            "level",
            "supervisor_name",
            "completion_pct",
            "status",
            "open_tasks",
            "delayed_tasks",
            "expected_completion",
        ]
    ].copy()

    display["status"] = display["status"].map(status_icons).fillna(display["status"])
    display["completion_pct"] = display["completion_pct"].apply(lambda x: f"{x:.1f}%")
    display["expected_completion"] = display["expected_completion"].apply(format_date)

    display.columns = [
        "Name",
        "Level",
        "Supervisor",
        "Completion",
        "Status",
        "Open Tasks",
        "Delayed Tasks",
        "Expected Completion",
    ]

    st.dataframe(display, use_container_width=True, hide_index=True)


# ── Page entry point ──────────────────────────────────────────────────────────


def main() -> None:
    auth = require_auth()
    render_sidebar(auth)

    if not any(has_role(auth, r) for r in [ROLE_SUPERVISOR, ROLE_ADMIN, ROLE_AUDITOR]):
        st.error(
            "🚫 Access Denied — This page is restricted to supervisors, admins, and auditors."
        )
        st.stop()

    _inject_styles()

    st.title("Class Standing")
    st.markdown("---")

    with st.spinner("Loading class standing…"):
        all_apprentices = load_class_standing()

    df = pd.DataFrame(all_apprentices)

    if df.empty:
        st.warning("No apprentice data available.")
        return

    # ── Filters ───────────────────────────────────────────────────────────────
    st.sidebar.markdown("### Filters")

    levels = ["All"] + sorted(df["level"].dropna().unique().tolist())
    selected_level = st.sidebar.selectbox("Apprenticeship Level", levels)

    supervisors = ["All"] + sorted(df["supervisor_name"].dropna().unique().tolist())
    selected_supervisor = st.sidebar.selectbox("Supervisor", supervisors)

    statuses = ["All", "On Track", "Delayed", "At Risk", "Completed"]
    selected_status = st.sidebar.selectbox("Status", statuses)

    # ── Apply filters ─────────────────────────────────────────────────────────
    filtered = df.copy()

    if selected_level != "All":
        filtered = filtered[filtered["level"] == selected_level]
    if selected_supervisor != "All":
        filtered = filtered[filtered["supervisor_name"] == selected_supervisor]
    if selected_status != "All":
        filtered = filtered[filtered["status"] == selected_status]

    # ── Render ────────────────────────────────────────────────────────────────
    _render_metrics(filtered)

    st.markdown("<br>", unsafe_allow_html=True)

    left_col, mid_col, right_col = st.columns([1.2, 1.5, 1.5])

    with left_col:
        _render_apprenticeship_level(filtered)
        st.markdown("<br>", unsafe_allow_html=True)
        _render_training_insights(filtered)

    with mid_col:
        _render_training_summary(filtered)

    with right_col:
        _render_docs_alerts(filtered)

    st.markdown("<br>", unsafe_allow_html=True)
    _render_roster(filtered)


main()
