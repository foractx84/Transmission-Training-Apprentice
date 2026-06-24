"""BigQuery service — data access layer for production data."""

from typing import Dict, List, Optional, Tuple
from google.cloud import bigquery
from datetime import datetime, timezone
from uuid import uuid4

from app.core.config import get_bigquery_config


def _get_client() -> bigquery.Client:
    """Return a BigQuery client using Application Default Credentials."""
    bq_config = get_bigquery_config()
    if not bq_config:
        raise RuntimeError(
            "BigQuery configuration not found. Check GCP_PROJECT and BQ_DATASET in .env"
        )
    return bigquery.Client(project=bq_config["project"])


def _table_ref(table_name: str) -> str:
    """Return fully-qualified table ID: project.dataset.table."""
    bq_config = get_bigquery_config()
    return f"{bq_config['project']}.{bq_config['dataset']}.{table_name}"


def insert_jpm_evaluation(
    evaluation: Dict,
    tasks: List[Dict],
) -> Tuple[bool, Optional[str]]:
    """
    Insert a JPM evaluation and its tasks into BigQuery.

    Args:
        evaluation: Single row dict matching the `evaluations` schema.
        tasks: List of row dicts matching the `evaluation_tasks` schema.

    Returns:
        (success, error_message) — error_message is None on success.
    """
    client = _get_client()

    # Insert parent row
    errors = client.insert_rows_json(_table_ref("evaluations"), [evaluation])
    if errors:
        return False, f"Error inserting evaluation: {errors}"

    # Insert child rows
    if tasks:
        errors = client.insert_rows_json(_table_ref("evaluation_tasks"), tasks)
        if errors:
            return False, f"Error inserting tasks: {errors}"

    return True, None

def insert_communication_log(
    evaluation_id: str,
    apprentice_id: str,
    apprentice_email: str | None,
    supervisor_email: str | None,
    recipient_email: str | None,
    recipient_type: str,
    email_type: str,
    subject: str,
    status: str,
    error_message: str | None = None,
) -> None:
    """Insert one communication/email attempt into BigQuery."""

    now = datetime.now(timezone.utc).isoformat()

    row = {
        "communication_id": str(uuid4()),
        "evaluation_id": evaluation_id,
        "apprentice_id": apprentice_id,
        "apprentice_email": apprentice_email,
        "supervisor_email": supervisor_email,
        "recipient_email": recipient_email,
        "recipient_type": recipient_type,
        "email_type": email_type,
        "subject": subject,
        "status": status,
        "error_message": error_message,
        "sent_at": now if status == "SENT" else None,
        "created_at": now,
    }

    client = _get_client()
    errors = client.insert_rows_json(_table_ref("communication_log"), [row])

    if errors:
        raise RuntimeError(f"Failed to insert communication log: {errors}")


def fetch_communication_log(
    email_type: str | None = None,
    limit: int = 200,
) -> List[Dict]:
    """Communication/email attempts from `communication_log`, newest first.

    If email_type is given (e.g. 'JPM_HOSD_CONFIRMATION'), restrict to that
    template type. Read-only — used by the Program Structure page's
    Communication Templates tab to show real sent history.
    """
    client = _get_client()
    type_filter = "WHERE email_type = @email_type" if email_type else ""

    sql = f"""
        SELECT
            communication_id,
            evaluation_id,
            apprentice_id,
            recipient_email,
            recipient_type,
            email_type,
            subject,
            status,
            error_message,
            sent_at,
            created_at
        FROM `{_table_ref("communication_log")}`
        {type_filter}
        ORDER BY created_at DESC
        LIMIT @limit
    """

    params = [bigquery.ScalarQueryParameter("limit", "INT64", limit)]
    if email_type:
        params.append(bigquery.ScalarQueryParameter("email_type", "STRING", email_type))

    job_config = bigquery.QueryJobConfig(query_parameters=params)
    rows = client.query(sql, job_config=job_config).result()
    return [
        {
            "communication_id": r["communication_id"],
            "evaluation_id":    r["evaluation_id"],
            "apprentice_id":    r["apprentice_id"],
            "recipient_email":  r["recipient_email"],
            "recipient_type":   r["recipient_type"],
            "email_type":       r["email_type"],
            "subject":          r["subject"],
            "status":           r["status"],
            "error_message":    r["error_message"],
            "sent_at":          r["sent_at"],
            "created_at":       r["created_at"],
        }
        for r in rows
    ]


def fetch_distinct_course_names(
    employee_ids: tuple[str, ...] | None = None,
) -> List[Dict]:
    """
    Return distinct task_name + course_id pairs from evaluations table.

    Args:
        employee_ids: If provided, restrict to evaluations whose apprentice_id is
            in this set — used to scope supervisor views by apprentice ownership.
            Pass None (admins) for no scope filter.

    Returned dict keeps the legacy `course_name` key for backwards compatibility
    with the picker UI, even though the underlying column is now `task_name`.
    """
    client = _get_client()
    ownership_filter = (
        "AND apprentice_id IN UNNEST(@employee_ids)" if employee_ids is not None else ""
    )

    sql = f"""
        SELECT DISTINCT
            course_id,
            task_name
        FROM `{_table_ref("evaluations")}`
        WHERE task_name IS NOT NULL
          AND course_id IS NOT NULL
          {ownership_filter}
        ORDER BY task_name
    """

    job_config = None
    if employee_ids is not None:
        job_config = bigquery.QueryJobConfig(
            query_parameters=[
                bigquery.ArrayQueryParameter(
                    "employee_ids", "STRING", list(employee_ids)
                )
            ]
        )

    rows = client.query(sql, job_config=job_config).result()
    return [{"course_id": r["course_id"], "course_name": r["task_name"]} for r in rows]


def fetch_evaluation_ids_for_course(
    course_name: str,
    employee_ids: tuple[str, ...] | None = None,
) -> List[Dict]:
    """
    Return list of evaluation_id + evaluation_date + apprentice_id + result
    for a given task_name so the user can pick a specific evaluation.

    Args:
        course_name: The task_name to filter by.
        employee_ids: If provided, restrict to evaluations whose apprentice_id is
            in this set — used to scope supervisor views by apprentice ownership.
    """
    client = _get_client()
    ownership_filter = (
        "AND apprentice_id IN UNNEST(@employee_ids)" if employee_ids is not None else ""
    )

    sql = f"""
        SELECT
            evaluation_id,
            evaluation_date,
            apprentice_id,
            result
        FROM `{_table_ref("evaluations")}`
        WHERE task_name = @course_name
          {ownership_filter}
        ORDER BY evaluation_date DESC
    """

    params = [bigquery.ScalarQueryParameter("course_name", "STRING", course_name)]
    if employee_ids is not None:
        params.append(
            bigquery.ArrayQueryParameter("employee_ids", "STRING", list(employee_ids))
        )

    job_config = bigquery.QueryJobConfig(query_parameters=params)
    rows = client.query(sql, job_config=job_config).result()
    return [
        {
            "evaluation_id": r["evaluation_id"],
            "evaluation_date": str(r["evaluation_date"]),
            "apprentice_id": r["apprentice_id"],
            "result": r["result"],
        }
        for r in rows
    ]


def fetch_evaluation_by_id(evaluation_id: str) -> Optional[Dict]:
    """Return full evaluation row + tasks for a given evaluation_id."""
    client = _get_client()

    # Fetch parent row
    eval_sql = f"""
        SELECT *
        FROM `{_table_ref("evaluations")}`
        WHERE evaluation_id = @evaluation_id
        LIMIT 1
    """
    job_config = bigquery.QueryJobConfig(
        query_parameters=[
            bigquery.ScalarQueryParameter("evaluation_id", "STRING", evaluation_id)
        ]
    )
    eval_rows = list(client.query(eval_sql, job_config=job_config).result())
    if not eval_rows:
        return None

    ev = dict(eval_rows[0])

    # Fetch child task rows
    task_sql = f"""
        SELECT task_index, task_description, score
        FROM `{_table_ref("evaluation_tasks")}`
        WHERE evaluation_id = @evaluation_id
        ORDER BY task_index
    """
    task_rows = list(client.query(task_sql, job_config=job_config).result())
    ev["tasks"] = [
        {
            "task_index": r["task_index"],
            "task_description": r["task_description"],
            "score": r["score"],
        }
        for r in task_rows
    ]

    return ev

def fetch_evaluation_codes() -> List[Dict]:
    """Distinct JPM/HOSD evaluations that have predefined questions.
    """
    client = _get_client()
    sql = f"""
        SELECT DISTINCT
            Evaluation_Code  AS evaluation_code,
            Evaluation_Type  AS evaluation_type,
            Evaluation_Title AS evaluation_title
        FROM `{_table_ref("Evaluation_Questions")}`
        WHERE Evaluation_Code IS NOT NULL
        ORDER BY evaluation_code
    """
    return [dict(row) for row in client.query(sql).result()]

def fetch_program_structure() -> List[Dict]:
    """Flat rows describing the program structure, from Evaluation_Questions.

    Each row: topic (Evaluation_Title), code (Evaluation_Code), type (JPM/HOSD),
    objective (Evaluation_Task_Objective), question (Evaluation_Question). The
    Program Structure page nests these into Topic → Form → Objective → Question.
    """
    client = _get_client()
    sql = f"""
        SELECT DISTINCT
            Evaluation_Title           AS topic,
            Evaluation_Code            AS code,
            Evaluation_Type            AS type,
            Evaluation_Task_Objective  AS objective,
            Evaluation_Question        AS question
        FROM `{_table_ref("Evaluation_Questions")}`
        WHERE Evaluation_Title IS NOT NULL
          AND Evaluation_Code IS NOT NULL
        ORDER BY topic, code, objective, question
    """
    return [dict(row) for row in client.query(sql).result()]


def fetch_evaluation_questions(evaluation_code: str) -> List[Dict]:
    """Return the ordered question/task definitions for one Evaluation_Code.

    Each row: question_id, evaluation_code, evaluation_type, evaluation_title,
    section_name, question_order, question_text. Empty list → no predefined
    questions (page falls back to manual task entry).
    """
    client = _get_client()
    sql = f"""
        SELECT
          CONCAT(
            REGEXP_REPLACE(Evaluation_Code, r'[^A-Za-z0-9]+', '_'),
            '_Q',
            CAST(ROW_NUMBER() OVER (
              PARTITION BY Evaluation_Code
              ORDER BY Evaluation_Task_Objective, Evaluation_Question
            ) AS STRING)
          )                                            AS question_id,
          Evaluation_Code            AS evaluation_code,
          Evaluation_Type            AS evaluation_type,
          Evaluation_Title           AS evaluation_title,
          Evaluation_Task_Objective  AS section_name,
          ROW_NUMBER() OVER (
            PARTITION BY Evaluation_Code
            ORDER BY Evaluation_Task_Objective, Evaluation_Question
          )                                            AS question_order,
          Evaluation_Question        AS question_text
        FROM `{_table_ref("Evaluation_Questions")}`
        WHERE Evaluation_Code = @evaluation_code
        ORDER BY question_order
    """
    job_config = bigquery.QueryJobConfig(
        query_parameters=[
            bigquery.ScalarQueryParameter("evaluation_code", "STRING", evaluation_code)
        ]
    )
    return [dict(row) for row in client.query(sql, job_config=job_config).result()]


SAP_EMPLOYEE_VIEW = "cnp-datafoundation-prod.SAP_REPORTING_VIEWS.SV_EMPLOYEE_ATTRIBUTES"


def fetch_employee_by_email(email: str) -> Optional[dict]:
    """
    Fetch employee record by email from SAP HR view.
    Returns dict with employee_id, full_name, email — or None if not found.
    """
    if not email or not email.strip():
        return None

    client = _get_client()
    sql = f"""
        SELECT
            EMPLOYEE_ID,
            FULL_NAME,
            EMAIL
        FROM `{SAP_EMPLOYEE_VIEW}`
        WHERE LOWER(EMAIL) = @email
        LIMIT 1
    """
    job_config = bigquery.QueryJobConfig(
        query_parameters=[
            bigquery.ScalarQueryParameter("email", "STRING", email.lower().strip())
        ]
    )
    rows = list(client.query(sql, job_config=job_config).result())
    if not rows:
        return None
    row = rows[0]
    return {
        "employee_id": row["EMPLOYEE_ID"],
        "full_name": row["FULL_NAME"],
        "email": row["EMAIL"],
    }


def fetch_apprentice_by_id(employee_id: str) -> Optional[dict]:
    """
    Fetch apprentice information by employee ID.

    Returns:
        Dict with name, level, supervisor_name, division, bu, etc.
        Or None if not found.
    """
    client = _get_client()

    sql = f"""
        SELECT DISTINCT
            employee_id,
            apprentice_name AS name,
            apprenticeship_level AS level,
            supervisor_name,
            division,
            bu
        FROM `{_table_ref("vw_apprentice_records")}`
        WHERE employee_id = @employee_id
        LIMIT 1
    """

    job_config = bigquery.QueryJobConfig(
        query_parameters=[
            bigquery.ScalarQueryParameter("employee_id", "STRING", employee_id)
        ]
    )

    rows = list(client.query(sql, job_config=job_config).result())

    if not rows:
        return None

    row = rows[0]
    return {
        "employee_id": row["employee_id"],
        "name": row["name"],
        "level": row["level"],
        "supervisor_name": row["supervisor_name"],
        "division": row["division"],
        "bu": row["bu"],
    }

def fetch_completed_evaluations(supervisor_name: str | None = None) -> List[Dict]:
    """Completed evaluation records for the Completed Documentation view.

    Joins `evaluations` → `evaluation_tasks` (average score) → vw_apprentice_records
    (employee name). When supervisor_name is given, restrict to evaluations that
    supervisor conducted — matching the Program Analytics records filter.

    Read-only: this never writes. Evaluations are entered on the JPM & HOSD page.
    """
    client = _get_client()
    supervisor_filter = "WHERE e.evaluator_name = @supervisor_name" if supervisor_name else ""

    sql = f"""
        SELECT
          e.evaluation_id               AS evaluation_id,
          e.apprentice_id               AS apprentice_id,
          ANY_VALUE(a.apprentice_name)  AS employee_name,
          e.task_name                   AS task_name,
          e.result                      AS result,
          e.evaluation_date             AS evaluation_date,
          e.evaluator_name              AS evaluator_name,
          e.evaluation_type             AS evaluation_type,
          e.form_version                AS form_version,
          e.submitted_at                AS submitted_at,
          ROUND(AVG(t.score), 1)        AS avg_score,
          COUNT(t.task_index)           AS task_count
        FROM `{_table_ref("evaluations")}` e
        LEFT JOIN `{_table_ref("evaluation_tasks")}` t
          ON t.evaluation_id = e.evaluation_id
        LEFT JOIN (
          SELECT DISTINCT employee_id, apprentice_name
          FROM `{_table_ref("vw_apprentice_records")}`
        ) a ON a.employee_id = e.apprentice_id
        {supervisor_filter}
        GROUP BY
          e.evaluation_id, e.apprentice_id, e.task_name, e.result,
          e.evaluation_date, e.evaluator_name, e.evaluation_type,
          e.form_version, e.submitted_at
        ORDER BY e.evaluation_date DESC
    """

    job_config = None
    if supervisor_name:
        job_config = bigquery.QueryJobConfig(
            query_parameters=[
                bigquery.ScalarQueryParameter("supervisor_name", "STRING", supervisor_name)
            ]
        )

    rows = client.query(sql, job_config=job_config).result()
    return [
        {
            "evaluation_id":   r["evaluation_id"],
            "apprentice_id":   r["apprentice_id"],
            "employee_name":   r["employee_name"],
            "task_name":       r["task_name"],
            "result":          r["result"],
            "evaluation_date": r["evaluation_date"],
            "evaluator_name":  r["evaluator_name"],
            "evaluation_type": r["evaluation_type"],
            "form_version":    r["form_version"],
            "submitted_at":    r["submitted_at"],
            "avg_score":       float(r["avg_score"]) if r["avg_score"] is not None else None,
            "task_count":      int(r["task_count"] or 0),
        }
        for r in rows
    ]