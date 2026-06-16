"""Analytics service — data loaders for the Apprentice Records page.

Replaces the development mocks in `data/mock_data.py` with real BigQuery
queries against `vw_apprentice_records`. Output dict shapes are intentionally
identical to the mocks so existing render functions need no changes.
"""

from __future__ import annotations

import html
import re
from datetime import date
import logging
import pandas as pd
import streamlit as st
from dotenv import load_dotenv
from google.cloud import bigquery
from google.auth.exceptions import DefaultCredentialsError
from google.api_core.exceptions import Forbidden, NotFound, BadRequest

from app.core.config import get_bigquery_config  # ← use shared config

load_dotenv()

logger = logging.getLogger(__name__)


# ── Remove old PROJECT_ID block entirely and replace with: ────────────────────


def _get_bq_config() -> dict:
    """
    Return BigQuery config using the shared get_bigquery_config().
    Shows st.error + st.stop instead of crashing with a stack trace.
    """
    bq_config = get_bigquery_config()
    if not bq_config:
        st.error(
            "BigQuery configuration not found. "
            "Please set GCP_PROJECT and BQ_DATASET in your .env file."
        )
        st.stop()
    return bq_config


@st.cache_resource
def _get_client() -> bigquery.Client:
    """Return a cached BigQuery client."""
    try:
        bq_config = _get_bq_config()
        return bigquery.Client(project=bq_config["project"])
    except DefaultCredentialsError as e:
        logger.error("BigQuery credentials error: %s", e)
        st.error("Authentication error. Please check your GCP credentials.")
        st.stop()


def _view_fqn() -> str:
    """Return fully-qualified view name: project.dataset.view."""
    bq_config = _get_bq_config()
    return f"{bq_config['project']}.{bq_config['dataset']}.vw_apprentice_records"


DATE_COLS = (
    "assigned_date",
    "completion_date",
    "expected_completion_date",
    "requal_date",
    "course_last_updated",
    "employment_start_date",
    "termination_date",
)


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------
def _coerce_dates(df: pd.DataFrame) -> pd.DataFrame:
    for col in DATE_COLS:
        if col in df.columns:
            df[col] = pd.to_datetime(df[col], errors="coerce")
    return df


def _to_date(val) -> date | None:
    """Convert pandas Timestamp / NaT / None → plain date or None."""
    if val is None or pd.isna(val):
        return None
    if isinstance(val, date) and not isinstance(val, pd.Timestamp):
        return val
    return pd.Timestamp(val).date()


def _clean_email(val) -> str:
    """Return a lower-cased, stripped email string.

    NULL emails arrive from BigQuery as float NaN (which is truthy), so a
    plain `(val or "")` leaves the NaN in place and `.lower()` then crashes.
    Guard with pd.isna() before treating the value as a string.
    """
    if val is None or (isinstance(val, float) and pd.isna(val)):
        return ""
    return str(val).lower().strip()


_TAG_RE = re.compile(r"<[^>]+>")
_WHITESPACE_RE = re.compile(r"\s+")


def _strip_html(value) -> str:
    """Remove HTML tags + decode entities + collapse whitespace."""
    if value is None or (isinstance(value, float) and pd.isna(value)):
        return ""
    text = str(value)
    text = _TAG_RE.sub(" ", text)
    text = html.unescape(text)
    text = text.replace("\xa0", " ")
    text = _WHITESPACE_RE.sub(" ", text)
    return text.strip()


# ---------------------------------------------------------------------------
# Loaders
# ---------------------------------------------------------------------------
@st.cache_data(ttl=3600, show_spinner="Loading apprentices…")
def load_apprentices() -> list[dict]:
    """
    Load summary record for all apprentices.
    Fields: id, name, email, level, enrolled_courses, open_tasks,
            delayed_tasks, program_alerts, start_date, expected_completion.
    Note: email field used for identity matching on Apprentice Records page.
    """
    try:
        sql = f"""
            SELECT
              employee_id                                  AS id,
              ANY_VALUE(apprentice_name)                   AS name,
              ANY_VALUE(LOWER(employee_email))             AS email,
              ANY_VALUE(apprenticeship_level)              AS level,
              COUNT(DISTINCT course_id)                    AS enrolled_courses,
              SUM(CAST(is_open_task    AS INT64))          AS open_tasks,
              SUM(CAST(is_delayed      AS INT64))          AS delayed_tasks,
              SUM(CAST(is_failed       AS INT64))
                + SUM(CAST(is_coming_due AS INT64))        AS program_alerts,
              MIN(assigned_date)                           AS start_date,
              MAX(expected_completion_date)                AS expected_completion
            FROM {_view_fqn()}
            WHERE apprentice_name IS NOT NULL
            GROUP BY employee_id
            ORDER BY name
        """
        df = _coerce_dates(
            _get_client().query(sql).to_dataframe(create_bqstorage_client=False)
        )
        return [
            {
                "id": row["id"],
                "name": row["name"],
                "level": row["level"],
                "email": _clean_email(row.get("email")),
                "enrolled_courses": int(row["enrolled_courses"] or 0),
                "open_tasks": int(row["open_tasks"] or 0),
                "delayed_tasks": int(row["delayed_tasks"] or 0),
                "program_alerts": int(row["program_alerts"] or 0),
                "start_date": _to_date(row["start_date"]),
                "expected_completion": _to_date(row["expected_completion"]),
            }
            for _, row in df.iterrows()
        ]
    except Forbidden as e:
        logger.error("BigQuery permission denied in load_apprentices: %s", e)
        st.error("Permission denied. You may not have access to this dataset.")
        return []
    except NotFound as e:
        logger.error("BigQuery resource not found in load_apprentices: %s", e)
        st.error("Data source not found. Please contact your administrator.")
        return []
    except BadRequest as e:
        logger.error("BigQuery bad request in load_apprentices: %s", e)
        st.error("Query error. Please contact your administrator.")
        return []
    except Exception as e:
        logger.error("Unexpected BigQuery error in load_apprentices: %s", e)
        st.error("An unexpected error occurred. Please try again later.")
        return []


# C3 FIX: Return pd.DataFrame() instead of [] on error
@st.cache_data(ttl=3600, show_spinner="Loading apprentice records…")
def load_apprentice_records_for(employee_id: str) -> pd.DataFrame:
    """All training records for one apprentice (server-side filter)."""
    try:
        sql = f"SELECT * FROM {_view_fqn()} WHERE employee_id = @eid"
        job = bigquery.QueryJobConfig(
            query_parameters=[
                bigquery.ScalarQueryParameter("eid", "STRING", employee_id)
            ]
        )
        return _coerce_dates(
            _get_client()
            .query(sql, job_config=job)
            .to_dataframe(create_bqstorage_client=False)
        )
    except Forbidden as e:
        logger.error(
            "BigQuery permission denied in load_apprentice_records_for(%s): %s",
            employee_id,
            e,
        )
        st.error("Permission denied loading training records.")
        return pd.DataFrame()  # ← C3 FIX: was []
    except Exception as e:
        logger.error("Error in load_apprentice_records_for(%s): %s", employee_id, e)
        st.error("Failed to load training records. Please try again later.")
        return pd.DataFrame()  # ← C3 FIX: was []


# ---------------------------------------------------------------------------
# Mock-shape derivers
# ---------------------------------------------------------------------------
def derive_milestones(records: pd.DataFrame) -> list[dict]:
    """
    Groups tasks by (apprenticeship_level, task_type) and assigns:
      * Completed   — all tasks completed
      * In Progress — some completed or in progress
      * Open        — none started
    """
    if records.empty:
        return []

    grouped = records.groupby(
        ["apprenticeship_level", "task_type"], as_index=False
    ).agg(
        total=("course_id", "count"),
        completed=("is_completed", "sum"),
        open_=("is_open_task", "sum"),
    )

    milestones: list[dict] = []
    for _, row in grouped.iterrows():
        if row["completed"] >= row["total"]:
            status = "Completed"
        elif row["completed"] > 0 or row["open_"] > 0:
            status = "In Progress"
        else:
            status = "Open"
        milestones.append(
            {
                "level": row["apprenticeship_level"],
                "name": row["task_type"],
                "status": status,
            }
        )

    order = {"Completed": 0, "In Progress": 1, "Open": 2}
    milestones.sort(key=lambda m: (order[m["status"]], m["level"], m["name"]))
    return milestones


def derive_training_summary(records: pd.DataFrame, limit: int = 25) -> list[dict]:
    """
    Most recent training activity.
    Field mapping:
        topic       ← task_name
        status      ← qual_status mapped to readable labels
        date        ← completion_date if present else assigned_date
        instructor  ← '—'  (not in source data)
        hours       ← course_duration_minutes / 60
        notes       ← course_description (truncated to 140 chars)
    """
    if records.empty:
        return []

    status_map = {
        "Complete": "Completed",
        "Current": "Completed",
        "Assigned": "Scheduled",
        "Coming Due": "Scheduled",
        "In Progress": "In Progress",
        "Past Due": "Past Due",
        "Failed": "Failed",
        "Suspended": "Suspended",
    }

    df = records.copy()
    df["activity_date"] = df["completion_date"].fillna(df["assigned_date"])
    df = df.sort_values("activity_date", ascending=False, na_position="last").head(
        limit
    )

    out: list[dict] = []
    for _, r in df.iterrows():
        notes = _strip_html(r.get("course_description"))
        if len(notes) > 140:
            notes = notes[:137] + "…"
        hours = (r.get("course_duration_minutes") or 0) / 60.0
        out.append(
            {
                "topic": r.get("task_name") or r.get("course_name") or "—",
                "status": status_map.get(
                    r.get("qual_status"), r.get("qual_status") or "—"
                ),
                "date": _to_date(r["activity_date"]),
                "instructor": "—",
                "hours": round(float(hours), 1),
                "notes": notes,
            }
        )
    return out


def derive_docs_alerts(records: pd.DataFrame) -> list[dict]:
    """
    Synthesizes alerts from training data:
      * High   — Past Due tasks
      * High   — Failed tasks
      * Medium — Coming Due tasks
      * Info   — most recent completion
    """
    if records.empty:
        return []

    alerts: list[dict] = []

    for _, r in records[records["qual_status"] == "Past Due"].head(5).iterrows():
        alerts.append(
            {
                "priority": "High",
                "type": "Alert",
                "message": f"Past due: {r['task_name']} (recert was due {_to_date(r['requal_date'])})",
            }
        )

    for _, r in records[records["qual_status"] == "Failed"].head(5).iterrows():
        score = int(r["score"]) if pd.notna(r.get("score")) else "—"
        alerts.append(
            {
                "priority": "High",
                "type": "Alert",
                "message": f"Failed: {r['task_name']} (score {score})",
            }
        )

    for _, r in records[records["qual_status"] == "Coming Due"].head(5).iterrows():
        alerts.append(
            {
                "priority": "Medium",
                "type": "Alert",
                "message": f"Recert due {_to_date(r['requal_date'])}: {r['task_name']}",
            }
        )

    completed = records[records["completion_date"].notna()].sort_values(
        "completion_date", ascending=False
    )
    if not completed.empty:
        r = completed.iloc[0]
        alerts.append(
            {
                "priority": "Info",
                "type": "Document",
                "message": f"Completed {_to_date(r['completion_date'])}: {r['task_name']}",
            }
        )

    return alerts


# C2 FIX: Add try-except to load_class_standing()
@st.cache_data(ttl=3600, show_spinner="Loading class standing…")
def load_class_standing() -> list[dict]:
    """Load all apprentices with progress metrics for Class Standing page."""
    try:
        sql = f"""
            SELECT
              employee_id                                       AS id,
              ANY_VALUE(apprentice_name)                        AS name,
              ANY_VALUE(LOWER(employee_email))                  AS email,
              ANY_VALUE(apprenticeship_level)                   AS level,
              ANY_VALUE(SUPERVISOR_NAME)                        AS supervisor_name,
              ANY_VALUE(Division)                               AS division,
              ANY_VALUE(BU)                                     AS bu,

              COUNT(DISTINCT course_id)                         AS enrolled_courses,
              SUM(CAST(is_completed    AS INT64))               AS completed_courses,
              SUM(CAST(is_open_task    AS INT64))               AS open_tasks,
              SUM(CAST(is_delayed      AS INT64))               AS delayed_tasks,
              SUM(CAST(is_failed       AS INT64))
                + SUM(CAST(is_coming_due AS INT64))             AS program_alerts,

              ROUND(
                SAFE_DIVIDE(
                  SUM(CAST(is_completed AS INT64)),
                  COUNT(DISTINCT course_id)
                ) * 100, 1
              )                                                 AS completion_pct,

              MAX(expected_completion_date)                     AS expected_completion,
              MIN(assigned_date)                                AS start_date,

              CASE
                WHEN SUM(CAST(is_failed  AS INT64)) > 0 THEN 'At Risk'
                WHEN SUM(CAST(is_delayed AS INT64)) > 0 THEN 'Delayed'
                WHEN SAFE_DIVIDE(
                       SUM(CAST(is_completed AS INT64)),
                       COUNT(DISTINCT course_id)
                     ) = 1.0                                    THEN 'Completed'
                ELSE 'On Track'
              END                                               AS status

            FROM {_view_fqn()}
            WHERE apprentice_name IS NOT NULL
            GROUP BY employee_id
            ORDER BY level, name
        """
        df = _coerce_dates(
            _get_client().query(sql).to_dataframe(create_bqstorage_client=False)
        )
        return [
            {
                "id": row["id"],
                "name": row["name"],
                "email": _clean_email(row.get("email")),
                "level": row.get("level") or "Unknown",
                "supervisor_name": row.get("supervisor_name") or "Unknown",
                "division": row.get("division") or "",
                "bu": row.get("bu") or "",
                "enrolled_courses": int(row["enrolled_courses"] or 0),
                "completed_courses": int(row["completed_courses"] or 0),
                "open_tasks": int(row["open_tasks"] or 0),
                "delayed_tasks": int(row["delayed_tasks"] or 0),
                "program_alerts": int(row["program_alerts"] or 0),
                "completion_pct": float(row["completion_pct"] or 0.0),
                "status": row.get("status") or "On Track",
                "expected_completion": _to_date(row["expected_completion"]),
                "start_date": _to_date(row["start_date"]),
            }
            for _, row in df.iterrows()
        ]
    except Forbidden as e:
        logger.error("BigQuery permission denied in load_class_standing: %s", e)
        st.error("Permission denied. You may not have access to this dataset.")
        return []
    except NotFound as e:
        logger.error("BigQuery resource not found in load_class_standing: %s", e)
        st.error("Data source not found. Please contact your administrator.")
        return []
    except BadRequest as e:
        logger.error("BigQuery bad request in load_class_standing: %s", e)
        st.error("Query error. Please contact your administrator.")
        return []
    except Exception as e:
        logger.error("Unexpected BigQuery error in load_class_standing: %s", e)
        st.error("An unexpected error occurred. Please try again later.")
        return []


def load_apprentice_by_email(email: str) -> dict | None:
    """
    Load a single apprentice record filtered server-side by email.
    No other apprentice data is returned — prevents PII exposure.
    Uses parameterized query to prevent SQL injection.
    """
    sql = f"""
        SELECT
          employee_id                                  AS id,
          ANY_VALUE(apprentice_name)                   AS name,
          ANY_VALUE(LOWER(employee_email))             AS email,
          ANY_VALUE(apprenticeship_level)              AS level,
          COUNT(DISTINCT course_id)                    AS enrolled_courses,
          SUM(CAST(is_open_task    AS INT64))          AS open_tasks,
          SUM(CAST(is_delayed      AS INT64))          AS delayed_tasks,
          SUM(CAST(is_failed       AS INT64))
            + SUM(CAST(is_coming_due AS INT64))        AS program_alerts,
          MIN(assigned_date)                           AS start_date,
          MAX(expected_completion_date)                AS expected_completion
        FROM {_view_fqn()}
        WHERE LOWER(employee_email) = @email
          AND apprentice_name IS NOT NULL
        GROUP BY employee_id
        LIMIT 1
    """
    job_config = bigquery.QueryJobConfig(
        query_parameters=[
            bigquery.ScalarQueryParameter("email", "STRING", email.lower().strip())
        ]
    )

    try:
        df = _coerce_dates(
            _get_client()
            .query(sql, job_config=job_config)
            .to_dataframe(create_bqstorage_client=False)
        )
    except Exception as e:
        logger.error("Error in load_apprentice_by_email(%s): %s", email, e)  # ← I1 FIX
        st.error("Failed to load your training record. Please try again later.")
        return None

    if df.empty:
        return None

    row = df.iloc[0]
    return {
        "id": row["id"],
        "name": row["name"],
        "email": _clean_email(row.get("email")),
        "level": row.get("level") or "Unknown",
        "enrolled_courses": int(row["enrolled_courses"] or 0),
        "open_tasks": int(row["open_tasks"] or 0),
        "delayed_tasks": int(row["delayed_tasks"] or 0),
        "program_alerts": int(row["program_alerts"] or 0),
        "start_date": _to_date(row["start_date"]),
        "expected_completion": _to_date(row["expected_completion"]),
    }


@st.cache_data(ttl=3600, show_spinner="Loading program analytics…")
def load_program_analytics(supervisor_name: str | None = None) -> list[dict]:
    """
    Load aggregated analytics per apprentice.
    If supervisor_name is provided, filter to that supervisor's apprentices only.
    """
    supervisor_filter = (
        "AND SUPERVISOR_NAME = @supervisor_name" if supervisor_name else ""
    )

    sql = f"""
        SELECT
          employee_id                                           AS id,
          ANY_VALUE(apprentice_name)                           AS name,
          ANY_VALUE(apprenticeship_level)                      AS level,
          ANY_VALUE(SUPERVISOR_NAME)                           AS supervisor_name,
          ANY_VALUE(Division)                                  AS division,
          ANY_VALUE(BU)                                        AS bu,

          COUNT(DISTINCT course_id)                            AS total_courses,
          SUM(CAST(is_completed  AS INT64))                    AS completed_courses,
          SUM(CAST(is_failed     AS INT64))                    AS failed_courses,
          SUM(CAST(is_delayed    AS INT64))                    AS delayed_courses,
          SUM(CAST(is_coming_due AS INT64))                    AS coming_due,

          ROUND(
            SAFE_DIVIDE(
              SUM(CAST(is_completed AS INT64)),
              COUNT(DISTINCT course_id)
            ) * 100, 1
          )                                                    AS completion_pct,

          ROUND(
            SAFE_DIVIDE(
              SUM(CAST(is_failed AS INT64)),
              COUNT(DISTINCT course_id)
            ) * 100, 1
          )                                                    AS fail_rate_pct,

          MIN(assigned_date)                                   AS start_date,
          MAX(completion_date)                                 AS completion_date,
          MAX(expected_completion_date)                        AS expected_completion,

          CASE
            WHEN SUM(CAST(is_failed  AS INT64)) > 0 THEN 'At Risk'
            WHEN SUM(CAST(is_delayed AS INT64)) > 0 THEN 'Delayed'
            WHEN SAFE_DIVIDE(
                   SUM(CAST(is_completed AS INT64)),
                   COUNT(DISTINCT course_id)
                 ) = 1.0                                       THEN 'Completed'
            ELSE 'On Track'
          END                                                  AS status

        FROM {_view_fqn()}
        WHERE apprentice_name IS NOT NULL
          {supervisor_filter}
        GROUP BY employee_id
        ORDER BY level, name
    """

    job_config = None
    if supervisor_name:
        from google.cloud import bigquery as bq

        job_config = bq.QueryJobConfig(
            query_parameters=[
                bq.ScalarQueryParameter("supervisor_name", "STRING", supervisor_name)
            ]
        )

    try:
        df = _coerce_dates(
            _get_client()
            .query(sql, job_config=job_config)
            .to_dataframe(create_bqstorage_client=False)
        )
        return [
            {
                "id": row["id"],
                "name": row["name"],
                "level": row.get("level") or "Unknown",
                "supervisor_name": row.get("supervisor_name") or "Unknown",
                "division": row.get("division") or "",
                "bu": row.get("bu") or "",
                "total_courses": int(row["total_courses"] or 0),
                "completed_courses": int(row["completed_courses"] or 0),
                "failed_courses": int(row["failed_courses"] or 0),
                "delayed_courses": int(row["delayed_courses"] or 0),
                "coming_due": int(row["coming_due"] or 0),
                "completion_pct": float(row["completion_pct"] or 0.0),
                "fail_rate_pct": float(row["fail_rate_pct"] or 0.0),
                "start_date": _to_date(row["start_date"]),
                "completion_date": _to_date(row["completion_date"]),
                "expected_completion": _to_date(row["expected_completion"]),
                "status": row.get("status") or "On Track",
            }
            for _, row in df.iterrows()
        ]
    except Forbidden:
        logger.error("Permission denied in load_program_analytics")
        st.error("Permission denied loading analytics data.")
        return []
    except Exception as e:
        logger.error("Error in load_program_analytics: %s", e)
        st.error("Failed to load analytics data. Please try again later.")
        return []


@st.cache_data(ttl=3600, show_spinner="Loading trend data…")
def load_analytics_trend(
    supervisor_name: str | None = None,
    employee_ids: tuple[str, ...] | None = None,
) -> list[dict]:
    """
    Load monthly completion trend grouped by completion_date.

    Args:
        supervisor_name: If provided, restrict to that supervisor's apprentices.
        employee_ids: If provided, restrict to completions belonging to that
            set of apprentice employee IDs. An empty tuple yields zero rows.
            Pass `None` to skip the IN-clause filter entirely.
    """
    from google.cloud import bigquery as bq

    filters: list[str] = [
        "completion_date IS NOT NULL",
        "apprentice_name IS NOT NULL",
        f"DATE(completion_date) >= DATE_SUB("
        f"(SELECT DATE(MAX(completion_date)) FROM {_view_fqn()}), INTERVAL 5 YEAR)",
    ]
    params: list = []

    if supervisor_name:
        filters.append("SUPERVISOR_NAME = @supervisor_name")
        params.append(
            bq.ScalarQueryParameter("supervisor_name", "STRING", supervisor_name)
        )

    if employee_ids is not None:
        filters.append("employee_id IN UNNEST(@employee_ids)")
        params.append(
            bq.ArrayQueryParameter("employee_ids", "STRING", list(employee_ids))
        )

    where_clause = " AND ".join(filters)

    sql = f"""
        SELECT
          FORMAT_DATE('%Y-%m', completion_date)   AS month,
          COUNT(*)                                AS completions,
          SUM(CAST(is_failed AS INT64))           AS failures,
          SUM(CAST(is_delayed AS INT64))          AS delays
        FROM {_view_fqn()}
        WHERE {where_clause}
        GROUP BY month
        ORDER BY month
    """

    job_config = bq.QueryJobConfig(query_parameters=params) if params else None

    try:
        df = (
            _get_client()
            .query(sql, job_config=job_config)
            .to_dataframe(create_bqstorage_client=False)
        )
        return df.to_dict("records")
    except Exception as e:
        logger.error("Error in load_analytics_trend: %s", e)
        return []
