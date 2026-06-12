"""
Apprentice Records page — individual apprentice training dashboard.
"""
import sys
from pathlib import Path
import pandas as pd
from html import escape

sys.path.insert(0, str(Path(__file__).parent.parent))

import streamlit as st
from app.components.navigation import require_auth, render_sidebar
from app.utils.formatters import format_date, format_hours
from app.utils.constants import COLOR_PRIMARY, COLOR_ACCENT
from app.services.analytics_service import (
    load_apprentice_by_email,
    load_apprentice_records_for,
    derive_milestones,
    derive_training_summary,
    derive_docs_alerts,
)
from app.core.rbac import has_role, ROLE_APPRENTICE

# ── Styles ────────────────────────────────────────────────────────────────────

def _inject_styles() -> None:
    st.markdown(
        f"""
        <style>
        /* Top metric pills */
        .metric-pill {{
            background-color: {COLOR_PRIMARY};
            color: white;
            padding: 10px 18px;
            border-radius: 20px;
            text-align: center;
        }}
        .metric-pill-label {{
            font-size: 0.72rem;
            opacity: 0.85;
            letter-spacing: 0.03em;
        }}
        .metric-pill-value {{
            font-size: 1.5rem;
            font-weight: 700;
            line-height: 1.2;
        }}
        .metric-pill-alert {{
            background-color: {COLOR_ACCENT};
        }}
        /* Card titles */
        .card-title {{
            font-size: 0.88rem;
            font-weight: 700;
            text-decoration: underline;
            margin-bottom: 6px;
        }}
        </style>
        """,
        unsafe_allow_html=True,
    )


# ── Top metric pills ──────────────────────────────────────────────────────────

def _render_metrics(apprentice: dict) -> None:
    metrics = [
        ("Enrolled Courses",    apprentice["enrolled_courses"],  False),
        ("Open Tasks",          apprentice["open_tasks"],         False),
        ("Delayed Tasks",       apprentice["delayed_tasks"],      apprentice["delayed_tasks"] > 0),
        ("Program Alerts",      apprentice["program_alerts"],     apprentice["program_alerts"] > 0),
        ("Expected Completion", format_date(apprentice["expected_completion"]), False),
    ]
    cols = st.columns(len(metrics))
    for col, (label, value, is_alert) in zip(cols, metrics):
        with col:
            alert_class = "metric-pill-alert" if is_alert else ""
            st.markdown(
                f"""
                <div class="metric-pill {alert_class}">
                    <div class="metric-pill-label">{escape(str(label))}</div>
                    <div class="metric-pill-value">{escape(str(value))}</div>
                </div>
                """,
                unsafe_allow_html=True,
            )


# ── Left column cards ─────────────────────────────────────────────────────────

def _render_apprenticeship_level(milestones: list[dict]) -> None:
    with st.container(border=True):
        st.markdown('<div class="card-title">Apprenticeship Level</div>', unsafe_allow_html=True)
        st.caption("Level Milestone Statuses")
        st.divider()

        STATUS_ICON = {
            "Completed":   "✅",
            "In Progress": "🔄",
            "Open":        "⭕",
        }
        if not milestones:
            st.caption("_No milestones available._")
            return
        for milestone in milestones:
            icon = STATUS_ICON.get(milestone["status"], "⭕")
            st.markdown(f"{icon} &nbsp; **{milestone['level']}** — {milestone['name']}")
            st.caption(f"&nbsp;&nbsp;&nbsp;&nbsp;&nbsp; {milestone['status']}")


def _render_training_insights(training_summary: list[dict]) -> None:
    with st.container(border=True):
        st.markdown('<div class="card-title">Training Insights</div>', unsafe_allow_html=True)
        st.caption("High points of training summary")
        st.divider()

        completed = [t for t in training_summary if t["status"] == "Completed"]
        scheduled = [t for t in training_summary if t["status"] == "Scheduled"]
        total_hours = sum(t["hours"] for t in completed)

        st.metric("Sessions Completed", len(completed))
        st.metric("Total Training Hours", format_hours(total_hours))
        st.metric("Upcoming Sessions", len(scheduled))

        if completed:
            st.caption(f"**Latest:** {completed[0]['topic']}")


# ── Middle column ─────────────────────────────────────────────────────────────

def _render_training_summary(training_summary: list[dict]) -> None:
    with st.container(border=True):
        st.markdown('<div class="card-title">Training Summary and Recommendations</div>', unsafe_allow_html=True)
        st.caption("Detailed list of training and insights from training")
        st.divider()

        STATUS_COLOR = {
            "Completed":   "🟢",
            "Scheduled":   "🔵",
            "In Progress": "🟡",
        }
        if not training_summary:
            st.caption("_No training records available._")
            return
        for training in training_summary:
            dot = STATUS_COLOR.get(training["status"], "⚪")
            st.markdown(f"{dot} &nbsp; **{training['topic']}**")
            cols = st.columns(3)
            cols[0].caption(f"📅 {format_date(training['date'])}")
            cols[1].caption(f"👤 {training['instructor']}")
            cols[2].caption(f"⏱️ {format_hours(training['hours'])}")
            if training.get("notes"):
                st.caption(f"_{training['notes']}_")
            st.divider()


# ── Right column ──────────────────────────────────────────────────────────────

def _render_docs_alerts(docs_alerts: list[dict]) -> None:
    with st.container(border=True):
        st.markdown('<div class="card-title">Documentation & Alerts</div>', unsafe_allow_html=True)
        st.caption(
            "Training documentation roadmap and alerts.\n\n"
            "*Forming program guiderails and following process through an auditable process*"
        )
        st.divider()

        PRIORITY_ICON = {"High": "🔴", "Medium": "🟡", "Info": "🔵"}
        TYPE_ICON = {"Alert": "⚠️", "Document": "📄"}

        if not docs_alerts:
            st.caption("_No alerts._")
            return
        for item in docs_alerts:
            priority_dot = PRIORITY_ICON.get(item["priority"], "⚪")
            type_icon = TYPE_ICON.get(item["type"], "📋")
            st.markdown(f"{priority_dot} {type_icon} &nbsp; {item['message']}")
            st.divider()


# ── Page entry point ──────────────────────────────────────────────────────────

def main() -> None:
    auth = require_auth()
    user_info = render_sidebar(auth)

    if not has_role(auth, ROLE_APPRENTICE):
        st.error("🚫 Access Denied — This page is only accessible to apprentices.")
        st.stop()

    current_user_email = (
        user_info.get("mail")
        or user_info.get("userPrincipalName")
        or ""
    ).lower().strip()

    display_name = user_info.get("displayName") or current_user_email

    if not current_user_email:
        st.error("Could not identify your account. Please log out and try again.")
        st.stop()

    _inject_styles()
    st.title("Apprentice Records")
    st.markdown("---")

    with st.spinner("Loading your record…"):
        apprentice = load_apprentice_by_email(current_user_email)  # ← server-side filter

    # ── If no BQ record found, use an empty template ──────────────────────────
    if apprentice is None:
        st.info(
            f"👋 Welcome, **{escape(display_name)}**. "   # ← I2 FIX: escape()
            "Your training record is not yet available. "
            "Please contact your administrator if you believe this is an error."
        )
        apprentice = {
            "id":                  None,
            "name":                display_name,
            "level":               None,
            "email":               current_user_email,
            "enrolled_courses":    0,
            "open_tasks":          0,
            "delayed_tasks":       0,
            "program_alerts":      0,
            "start_date":          None,
            "expected_completion": None,
        }
        empty_df         = pd.DataFrame()
        milestones       = derive_milestones(empty_df)
        training_summary = derive_training_summary(empty_df)
        docs_alerts      = derive_docs_alerts(empty_df)
    else:
        records          = load_apprentice_records_for(apprentice["id"])
        milestones       = derive_milestones(records)
        training_summary = derive_training_summary(records)
        docs_alerts      = derive_docs_alerts(records)

    # ── Render ────────────────────────────────────────────────────────────────
    st.markdown("<br>", unsafe_allow_html=True)

    _render_metrics(apprentice)

    st.markdown("<br>", unsafe_allow_html=True)

    left_col, mid_col, right_col = st.columns([1.2, 1.5, 1.5])

    with left_col:
        _render_apprenticeship_level(milestones)
        st.markdown("<br>", unsafe_allow_html=True)
        _render_training_insights(training_summary)

    with mid_col:
        _render_training_summary(training_summary)

    with right_col:
        _render_docs_alerts(docs_alerts)


main()
