"""BigQuery service — data access layer for production data."""
from typing import Dict, List, Optional, Tuple
from google.cloud import bigquery

from app.core.config import get_bigquery_config


def _get_client() -> bigquery.Client:
    """Return a BigQuery client using Application Default Credentials."""
    bq_config = get_bigquery_config()
    if not bq_config:
        raise RuntimeError("BigQuery configuration not found. Check GCP_PROJECT and BQ_DATASET in .env")
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


def fetch_distinct_course_names(supervisor_name: str | None = None) -> List[Dict]:
    """
    Return distinct task_name + course_id pairs from evaluations table.
    If supervisor_name provided, filter by evaluator_name (the supervisor/observer).
    Returned dict keeps the legacy `course_name` key for backwards compatibility
    with the picker UI, even though the underlying column is now `task_name`.
    """
    client = _get_client()
    supervisor_filter = "AND evaluator_name = @supervisor_name" if supervisor_name else ""

    sql = f"""
        SELECT DISTINCT
            course_id,
            task_name
        FROM `{_table_ref("evaluations")}`
        WHERE task_name IS NOT NULL
          AND course_id IS NOT NULL
          {supervisor_filter}
        ORDER BY task_name
    """

    job_config = None
    if supervisor_name:
        job_config = bigquery.QueryJobConfig(
            query_parameters=[
                bigquery.ScalarQueryParameter("supervisor_name", "STRING", supervisor_name)
            ]
        )

    rows = client.query(sql, job_config=job_config).result()
    return [{"course_id": r["course_id"], "course_name": r["task_name"]} for r in rows]


def fetch_evaluation_ids_for_course(
    course_name: str,
    supervisor_name: str | None = None,
) -> List[Dict]:
    """
    Return list of evaluation_id + evaluation_date + apprentice_id + result
    for a given task_name so the user can pick a specific evaluation.
    """
    client = _get_client()
    supervisor_filter = "AND evaluator_name = @supervisor_name" if supervisor_name else ""

    sql = f"""
        SELECT
            evaluation_id,
            evaluation_date,
            apprentice_id,
            result
        FROM `{_table_ref("evaluations")}`
        WHERE task_name = @course_name
          {supervisor_filter}
        ORDER BY evaluation_date DESC
    """

    params = [bigquery.ScalarQueryParameter("course_name", "STRING", course_name)]
    if supervisor_name:
        params.append(bigquery.ScalarQueryParameter("supervisor_name", "STRING", supervisor_name))

    job_config = bigquery.QueryJobConfig(query_parameters=params)
    rows = client.query(sql, job_config=job_config).result()
    return [
        {
            "evaluation_id":   r["evaluation_id"],
            "evaluation_date": str(r["evaluation_date"]),
            "apprentice_id":   r["apprentice_id"],
            "result":          r["result"],
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
            "task_index":       r["task_index"],
            "task_description": r["task_description"],
            "score":            r["score"],
        }
        for r in task_rows
    ]

    return ev


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
