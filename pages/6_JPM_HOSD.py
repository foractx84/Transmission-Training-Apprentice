"""JPM & HOSD Evaluation Form Submission."""
import sys
import logging
from pathlib import Path
from datetime import datetime, date, timezone
from html import escape
import uuid

sys.path.insert(0, str(Path(__file__).parent.parent))

import streamlit as st
import pypdfium2 as pdfium

from app.components.navigation import require_auth, render_sidebar
from app.core.rbac import has_role, ROLE_SUPERVISOR, ROLE_ADMIN
from app.services.bigquery_service import (
    insert_jpm_evaluation,
    fetch_employee_by_email,
)
from app.services.analytics_service import load_class_standing
from app.services.sharepoint_service import (
    list_sharepoint_folder_items,
    download_file_from_sharepoint,
)
from app.services.gcs_service import (
    upload_file_to_gcs,
    list_files_in_gcs_folder,
    download_file_from_gcs,
)
from app.core.config import get_config

logger = logging.getLogger(__name__)


# ── Styles ────────────────────────────────────────────────────────────────────

def _inject_styles() -> None:
    st.markdown(
        """
        <style>
        /* All form controls — uniform compact height to match .readonly-field */
        /* Selectbox: zero padding at every nested level */
        [data-testid="stSelectbox"] [data-baseweb="select"],
        [data-testid="stSelectbox"] [data-baseweb="select"] > div,
        [data-testid="stSelectbox"] [data-baseweb="select"] > div > div,
        [data-testid="stSelectbox"] [data-baseweb="select"] > div > div > div,
        [data-testid="stSelectbox"] [role="combobox"] {
            padding-top: 0 !important;
            padding-bottom: 0 !important;
        }
        /* Enforce 2rem height with flex centering at every level */
        [data-testid="stSelectbox"] [data-baseweb="select"] > div {
            min-height: 2rem !important;
            height: 2rem !important;
            display: flex !important;
            align-items: center !important;
        }
        [data-testid="stSelectbox"] [data-baseweb="select"] > div > div {
            min-height: 2rem !important;
            display: flex !important;
            align-items: center !important;
            line-height: 1 !important;
        }
        /* Selectbox arrow — shrink */
        [data-testid="stSelectbox"] [data-baseweb="select"] svg {
            width: 1rem;
            height: 1rem;
        }
        /* Text / Date / Number inputs: zero vertical padding so text centers naturally */
        div[data-baseweb="input"] {
            min-height: 2rem !important;
        }
        div[data-baseweb="input"] > input,
        .stTextInput input,
        .stDateInput input,
        .stNumberInput input {
            height: 2rem !important;
            min-height: 2rem !important;
            padding-top: 0 !important;
            padding-bottom: 0 !important;
            font-size: 0.88rem !important;
        }
        .stTextArea textarea {
            font-size: 0.88rem !important;
            padding-top: 0.35rem !important;
            padding-bottom: 0.35rem !important;
        }
        .stButton > button {
            min-height: 2rem !important;
            padding-top: 0.2rem !important;
            padding-bottom: 0.2rem !important;
            font-size: 0.88rem !important;
        }
        .stRadio label {
            font-size: 0.88rem !important;
        }
        /* Tighten label spacing above widgets */
        .stSelectbox label,
        .stTextInput label,
        .stDateInput label,
        .stNumberInput label,
        .stTextArea label,
        .stRadio > label {
            margin-bottom: 0.2rem !important;
            padding-bottom: 0 !important;
        }
        .section-header {
            font-size: 0.82rem;
            font-weight: 700;
            color: #e2e8f0;
            letter-spacing: 0.06em;
            text-transform: uppercase;
            border-left: 3px solid #4299e1;
            padding-left: 0.6rem;
            margin: 0.8rem 0 0.35rem 0;
        }
        .section-divider {
            border-top: 1px solid #2d3748;
            margin: 0.8rem 0;
        }
        .readonly-label {
            color: #a0aec0;
            font-size: 0.68rem;
            text-transform: uppercase;
            letter-spacing: 0.05em;
            margin-bottom: 0.1rem;
        }
        .readonly-field {
            background: #1e2130;
            padding: 0.35rem 0.7rem;
            border-radius: 6px;
            border: 1px solid #2d3748;
            color: #cbd5e0;
            margin-bottom: 0.4rem;
            font-size: 0.88rem;
            min-height: 1.9rem;
            display: flex;
            align-items: center;
        }
        .apprentice-card {
            background: linear-gradient(135deg, #1e2130 0%, #232838 100%);
            padding: 0.7rem 1rem;
            border-radius: 8px;
            border: 1px solid #2d3748;
            margin: 0.35rem 0 0.7rem 0;
        }
        .apprentice-card-name {
            font-size: 0.98rem;
            font-weight: 700;
            color: #f7fafc;
            margin-bottom: 0.25rem;
        }
        .apprentice-card-meta {
            color: #a0aec0;
            font-size: 0.78rem;
            margin: 0.1rem 0;
        }
        .apprentice-card-meta strong {
            color: #cbd5e0;
            font-weight: 600;
        }
        .result-badge {
            padding: 0.5rem 1rem;
            border-radius: 8px;
            font-weight: 700;
            display: flex;
            justify-content: space-between;
            align-items: center;
            font-size: 0.95rem;
        }
        .result-pass {
            background: #276749;
            color: #f0fff4;
            border: 1px solid #38a169;
        }
        .result-fail {
            background: #9b2c2c;
            color: #fff5f5;
            border: 1px solid #e53e3e;
        }
        .result-pending {
            background: #1e2130;
            color: #a0aec0;
            border: 1px dashed #2d3748;
        }
        .result-avg {
            font-size: 0.8rem;
            font-weight: 500;
            opacity: 0.85;
        }
        .sync-pill {
            display: inline-block;
            background: #1e2130;
            border: 1px solid #2d3748;
            color: #a0aec0;
            padding: 0.3rem 0.8rem;
            border-radius: 20px;
            font-size: 0.78rem;
        }
        .sync-pill-ok {
            color: #9ae6b4;
            border-color: #2f855a;
        }
        .score-row-label {
            color: #cbd5e0;
            font-weight: 600;
            padding-top: 0.2rem;
            margin-bottom: 0.3rem;
            font-size: 0.9rem;
        }
        </style>
        """,
        unsafe_allow_html=True,
    )


# ── Helpers ───────────────────────────────────────────────────────────────────

def _pretty_task_name(filename: str) -> str:
    """Strip `.pdf` and normalize separators for display."""
    name = filename.rsplit(".", 1)[0]
    return name.replace("_", " ").strip()


@st.cache_data(ttl=60, show_spinner=False)
def _list_pdfs(bucket: str) -> list[str]:
    return list_files_in_gcs_folder(bucket)


@st.cache_data(ttl=300, show_spinner=False)
def _download_pdf(bucket: str, filename: str) -> bytes:
    return download_file_from_gcs(bucket, filename)


@st.cache_data(ttl=3600, show_spinner=False)
def _lookup_evaluator(email: str) -> dict | None:
    try:
        return fetch_employee_by_email(email)
    except Exception as e:
        logger.error("Evaluator lookup failed for %s: %s", email, e)
        return None


# ── Sync Function ─────────────────────────────────────────────────────────────

def sync_sharepoint_to_gcs(
    auth_token: str,
    site_id: str,
    drive_id: str,
    folder_path: str,
    gcs_bucket: str,
) -> tuple[bool, str, int]:
    """Sync new PDFs from SharePoint to GCS. Returns (ok, message, uploaded_count)."""
    try:
        sp_files = list_sharepoint_folder_items(auth_token, site_id, drive_id, folder_path)
        pdf_files = [f for f in sp_files if f["name"].lower().endswith(".pdf")]
        if not pdf_files:
            return False, "No PDF files found in SharePoint folder.", 0

        # Always overwrite so SharePoint revisions reach GCS even when the filename is unchanged.
        for f in pdf_files:
            file_bytes = download_file_from_sharepoint(auth_token, site_id, drive_id, f["id"])
            upload_file_to_gcs(gcs_bucket, file_bytes, f["name"])

        return True, f"Sync complete — {len(pdf_files)} PDF(s) mirrored to GCS.", len(pdf_files)
    except Exception as e:
        return False, f"Sync failed: {e}", 0


# ── PDF Preview ───────────────────────────────────────────────────────────────

def render_pdf_preview(pdf_bytes: bytes) -> None:
    """Render the first page of a PDF as an image."""
    try:
        pdf = pdfium.PdfDocument(pdf_bytes)
        page = pdf[0]
        image = page.render(scale=2).to_pil()
        st.image(image, use_container_width=True)
    except Exception as e:
        st.error(f"Could not render PDF: {e}")


# ── Sub-sections ──────────────────────────────────────────────────────────────

def _render_sync_section(config: dict) -> None:
    site_id = config.get("SITE_2_ID")
    drive_id = config.get("DRIVE_2_ID")
    folder_path = config.get("Folder_2_path")
    gcs_bucket = config.get("GCS_BUCKET")

    with st.expander("📁 SharePoint Sync", expanded=False):
        st.caption("Pull the latest JPM/HOSD PDF forms from SharePoint into the storage bucket.")
        c1, c2 = st.columns([1, 2])
        with c1:
            if st.button("🔄 Sync from SharePoint", use_container_width=True):
                with st.spinner("Syncing PDFs from SharePoint…"):
                    ok, msg, _ = sync_sharepoint_to_gcs(
                        st.session_state.auth_token,
                        site_id, drive_id, folder_path, gcs_bucket,
                    )
                st.session_state.sync_timestamp = datetime.now()
                st.session_state.sync_result = (ok, msg)
                _list_pdfs.clear()
                st.rerun()
        with c2:
            ts = st.session_state.get("sync_timestamp")
            if ts:
                st.markdown(
                    f'<div class="sync-pill sync-pill-ok">✓ Last synced: '
                    f'{ts.strftime("%Y-%m-%d %H:%M:%S")}</div>',
                    unsafe_allow_html=True,
                )
            else:
                st.markdown(
                    '<div class="sync-pill">Not synced this session</div>',
                    unsafe_allow_html=True,
                )

        result = st.session_state.get("sync_result")
        if result:
            ok, msg = result
            (st.success if ok else st.error)(msg, icon="✅" if ok else "❌")


def _render_task_selector(gcs_bucket: str) -> str | None:
    task_files = _list_pdfs(gcs_bucket)
    if not task_files:
        st.warning("No PDF forms found. Open **SharePoint Sync** above and click Sync.")
        return None

    return st.selectbox(
        "Evaluation Form",
        options=task_files,
        format_func=_pretty_task_name,
        key="selected_task",
        help="Choose the JPM/HOSD form for this evaluation.",
    )


def _render_pdf_panel(gcs_bucket: str, selected_task: str | None) -> None:
    if not selected_task:
        st.info("Select a form to preview it here.")
        return

    pdf_bytes = _download_pdf(gcs_bucket, selected_task)
    with st.container(border=True):
        render_pdf_preview(pdf_bytes)

    st.download_button(
        label="📥 Download PDF",
        data=pdf_bytes,
        file_name=selected_task,
        mime="application/pdf",
        use_container_width=True,
    )


def _render_apprentice_card(info: dict) -> None:
    st.markdown(
        f"""
        <div class="apprentice-card">
            <div class="apprentice-card-name">{escape(info.get("name") or "—")}</div>
            <div class="apprentice-card-meta">
                <strong>Employee ID:</strong> {escape(str(info.get("employee_id") or "—"))}
                &nbsp;·&nbsp; <strong>Level:</strong> {escape(info.get("level") or "—")}
            </div>
            <div class="apprentice-card-meta">
                <strong>Supervisor:</strong> {escape(info.get("supervisor_name") or "—")}
            </div>
            <div class="apprentice-card-meta">
                <strong>Division:</strong> {escape(info.get("division") or "—")}
                &nbsp;·&nbsp; <strong>BU:</strong> {escape(info.get("bu") or "—")}
            </div>
        </div>
        """,
        unsafe_allow_html=True,
    )


def _render_apprentice_section() -> dict | None:
    st.markdown('<div class="section-header">👤 Apprentice</div>', unsafe_allow_html=True)

    apprentices = load_class_standing()
    if not apprentices:
        st.warning("No apprentices available.")
        return None

    apprentice_map = {a["id"]: a for a in apprentices}

    selected_id = st.selectbox(
        "Apprentice Employee ID",
        options=list(apprentice_map.keys()),
        format_func=lambda emp_id: f"{emp_id} — {apprentice_map[emp_id]['name']}",
        index=None,
        placeholder="Type Employee ID or name to search…",
        key="apprentice_selected_id",
        label_visibility="collapsed",
    )

    if not selected_id:
        return None

    a = apprentice_map[selected_id]
    info = {
        "employee_id":      a["id"],
        "name":             a.get("name"),
        "level":            a.get("level"),
        "supervisor_name":  a.get("supervisor_name"),
        "division":         a.get("division"),
        "bu":               a.get("bu"),
    }
    _render_apprentice_card(info)
    return info


def _render_evaluator_section(user_info: dict) -> tuple[str, str]:
    st.markdown('<div class="section-header">👨‍⚖️ Evaluator</div>', unsafe_allow_html=True)

    email = user_info.get("mail") or user_info.get("userPrincipalName") or ""
    fallback_name = user_info.get("displayName") or ""

    sap_record = _lookup_evaluator(email) if email else None
    if sap_record:
        evaluator_emp_id = sap_record.get("employee_id") or ""
        evaluator_name = sap_record.get("full_name") or fallback_name
    else:
        evaluator_emp_id = ""
        evaluator_name = fallback_name

    c1, c2 = st.columns(2)
    with c1:
        st.markdown('<div class="readonly-label">Employee ID</div>', unsafe_allow_html=True)
        st.markdown(
            f'<div class="readonly-field">{escape(evaluator_emp_id) or "—"}</div>',
            unsafe_allow_html=True,
        )
    with c2:
        st.markdown('<div class="readonly-label">Name</div>', unsafe_allow_html=True)
        st.markdown(
            f'<div class="readonly-field">{escape(evaluator_name) or "—"}</div>',
            unsafe_allow_html=True,
        )

    # Fall back to email for audit trail if SAP lookup didn't resolve an ID.
    return (evaluator_emp_id or email), evaluator_name


def _render_evaluation_details() -> tuple[date, str, str, datetime]:
    st.markdown('<div class="section-header">📊 Details</div>', unsafe_allow_html=True)
    c1, c2, c3 = st.columns(3)
    with c1:
        evaluation_date = st.date_input("Evaluation Date", value=date.today())
    with c2:
        evaluation_type = st.selectbox(
            "Evaluation Type",
            options=["Field", "Performance", "Simulation"],
            key="evaluation_type",
        )
    with c3:
        form_version = st.selectbox(
            "Form Version",
            options=[f"v{n}.0" for n in range(1, 6)],
            key="form_version",
        )

    started_at = st.session_state.form_start_time
    st.caption(f"⏱ Form opened at {started_at.strftime('%H:%M:%S')}")
    return evaluation_date, evaluation_type.lower(), form_version, started_at


def _render_task_scores() -> list[dict]:
    st.markdown('<div class="section-header">⭐ Task Scores</div>', unsafe_allow_html=True)
    st.caption(
        "Describe and rate each sub-task on a 1–5 scale. "
        "**Every sub-task must score 3 or higher to pass.** "
        "Sub-tasks scoring below 3 require a comment explaining why."
    )

    c_count, _ = st.columns([1, 4])
    with c_count:
        num_tasks = st.number_input(
            "Number of Sub-Tasks",
            min_value=1, max_value=20, value=1, step=1,
            key="num_tasks",
        )

    tasks: list[dict] = []
    for idx in range(1, num_tasks + 1):
        with st.container(border=True):
            score_val = st.session_state.get(f"score_{idx}")
            is_failing = score_val is not None and score_val < 3

            header = f"Sub-Task {idx}"
            if is_failing:
                header += " &nbsp;<span style='color:#fc8181;'>⚠ Fail</span>"
            st.markdown(
                f'<div class="score-row-label">{header}</div>',
                unsafe_allow_html=True,
            )

            c_desc, c_score = st.columns([3, 2], gap="large")
            with c_desc:
                st.markdown('<div class="readonly-label">Description</div>', unsafe_allow_html=True)
                description = st.text_input(
                    f"Sub-Task {idx} description",
                    key=f"task_desc_{idx}",
                    placeholder=f"Describe sub-task {idx} (e.g. “Set up grounds on conductor”)",
                    label_visibility="collapsed",
                )
            with c_score:
                st.markdown('<div class="readonly-label">Score (1–5)</div>', unsafe_allow_html=True)
                score = st.radio(
                    f"Sub-Task {idx} score",
                    options=[1, 2, 3, 4, 5],
                    horizontal=True,
                    index=None,
                    key=f"score_{idx}",
                    label_visibility="collapsed",
                )

            comment = ""
            if score is not None and score < 3:
                st.markdown(
                    '<div style="color:#fc8181; font-size:0.8rem; margin-top:0.4rem;">'
                    '⚠ Comment required — explain why this sub-task scored below 3'
                    '</div>',
                    unsafe_allow_html=True,
                )
                comment = st.text_area(
                    f"Sub-Task {idx} failure comment",
                    key=f"task_comment_{idx}",
                    placeholder="Why did the apprentice score below 3 on this sub-task?",
                    height=80,
                    label_visibility="collapsed",
                )

            tasks.append({
                "task_index":       idx,
                "task_description": description.strip(),
                "score":            score,
                "comment":          (comment or "").strip(),
            })
    return tasks


def _render_result_preview(tasks: list[dict]) -> str | None:
    st.markdown('<div class="section-header">🎯 Result</div>', unsafe_allow_html=True)

    total = len(tasks)
    rated = [t for t in tasks if t["score"] is not None]
    remaining = total - len(rated)
    if remaining > 0:
        st.markdown(
            f'<div class="result-badge result-pending">'
            f'<span>⏳ Rate all sub-tasks to see result</span>'
            f'<span class="result-avg">{remaining} remaining</span></div>',
            unsafe_allow_html=True,
        )
        return None

    failing = [t for t in tasks if t["score"] < 3]
    if not failing:
        st.markdown(
            f'<div class="result-badge result-pass">'
            f'<span>✅ PASS</span>'
            f'<span class="result-avg">All {total} sub-tasks ≥ 3</span></div>',
            unsafe_allow_html=True,
        )
        return "PASS"

    st.markdown(
        f'<div class="result-badge result-fail">'
        f'<span>❌ FAIL</span>'
        f'<span class="result-avg">{len(failing)} of {total} sub-task(s) below 3</span></div>',
        unsafe_allow_html=True,
    )
    return "FAIL"


def _reset_form() -> None:
    st.session_state.form_start_time = datetime.now()
    keys_to_clear = {
        "apprentice_selected_id", "comments",
        "evaluation_type", "form_version", "selected_task", "num_tasks",
        "sync_result",
    }
    per_task_prefixes = ("score_", "task_desc_", "task_comment_")
    for k in list(st.session_state.keys()):
        if k in keys_to_clear or k.startswith(per_task_prefixes):
            st.session_state.pop(k, None)


def _validate_tasks(tasks: list[dict]) -> list[str]:
    """Return a list of human-readable validation errors. Empty if valid."""
    errors: list[str] = []
    for t in tasks:
        idx = t["task_index"]
        if not t["task_description"]:
            errors.append(f"Sub-Task {idx}: description is required.")
        if t["score"] is None:
            errors.append(f"Sub-Task {idx}: score is required.")
        elif t["score"] < 3 and not t["comment"]:
            errors.append(f"Sub-Task {idx}: comment required (score below 3).")
    return errors


def _merge_failure_comments(eval_comments: str, tasks: list[dict]) -> str:
    """Append per-task failure comments into the evaluation-level comments field."""
    failing = [t for t in tasks if t["score"] is not None and t["score"] < 3 and t["comment"]]
    if not failing:
        return eval_comments

    bullets = [
        f"- Sub-Task {t['task_index']} ({t['task_description']}, score {t['score']}): {t['comment']}"
        for t in failing
    ]
    section = "Sub-task failure comments:\n" + "\n".join(bullets)
    return f"{eval_comments}\n\n{section}" if eval_comments.strip() else section


def _submit_evaluation(payload: dict, tasks: list[dict]) -> None:
    with st.spinner("Submitting evaluation…"):
        ok, err = insert_jpm_evaluation(evaluation=payload, tasks=tasks)
    if ok:
        st.success("Evaluation submitted successfully!", icon="✅")
        st.balloons()
        _reset_form()
        st.rerun()
    else:
        st.error(f"Submission failed: {err}", icon="❌")


# ── Main Page ─────────────────────────────────────────────────────────────────

def main() -> None:
    auth = require_auth()
    user_info = render_sidebar(auth)

    if not (has_role(auth, ROLE_SUPERVISOR) or has_role(auth, ROLE_ADMIN)):
        st.error("🚫 Access Denied — This page is for supervisors and admins only.")
        st.stop()

    _inject_styles()

    config = get_config()
    required = ["SITE_2_ID", "DRIVE_2_ID", "Folder_2_path", "GCS_BUCKET"]
    missing = [k for k in required if not config.get(k)]
    if missing:
        st.error(f"❌ Configuration missing: {', '.join(missing)}. Contact admin.")
        st.stop()

    gcs_bucket = config["GCS_BUCKET"]

    if "form_start_time" not in st.session_state:
        st.session_state.form_start_time = datetime.now()

    st.title("📝 JPM & HOSD Evaluation")
    st.caption("Submit a Job Performance Measure or HOSD evaluation record.")

    _render_sync_section(config)

    st.markdown('<div class="section-divider"></div>', unsafe_allow_html=True)

    col_pdf, col_form = st.columns([1, 1], gap="large")

    with col_pdf:
        st.markdown('<div class="section-header">📋 Form Preview</div>', unsafe_allow_html=True)
        selected_task = _render_task_selector(gcs_bucket)
        _render_pdf_panel(gcs_bucket, selected_task)

    with col_form:
        apprentice_info = _render_apprentice_section()
        evaluator_emp_id, evaluator_name = _render_evaluator_section(user_info)
        evaluation_date, evaluation_type, form_version, started_at = _render_evaluation_details()

    # ── Full-width below the 2-col section ──────────────────────────────────
    st.markdown('<div class="section-divider"></div>', unsafe_allow_html=True)
    scores = _render_task_scores()

    st.markdown('<div class="section-header">📝 Comments</div>', unsafe_allow_html=True)
    comments = st.text_area(
        "Comments",
        height=120,
        key="comments",
        placeholder="Optional — observations, remedial notes, etc.",
        label_visibility="collapsed",
    )

    result_data = _render_result_preview(scores)

    st.markdown('<div class="section-divider"></div>', unsafe_allow_html=True)

    b1, b2 = st.columns([5, 1])
    with b1:
        submit_clicked = st.button(
            "✅ Submit Evaluation",
            type="primary",
            use_container_width=True,
            disabled=result_data is None,
        )
    with b2:
        if st.button("↺ Reset", use_container_width=True):
            _reset_form()
            st.rerun()

    if submit_clicked:
        errors: list[str] = []
        if not apprentice_info:
            errors.append("Select an apprentice.")
        if not selected_task:
            errors.append("Select an Evaluation Form.")
        errors.extend(_validate_tasks(scores))
        if not result_data:
            errors.append("Rate all sub-tasks before submitting.")
        if errors:
            for e in errors:
                st.error(e)
            return

        result = result_data
        evaluation_id = str(uuid.uuid4())
        duration_seconds = int((datetime.now() - started_at).total_seconds())
        merged_comments = _merge_failure_comments(comments, scores)
        task_rows = [
            {
                "evaluation_id":    evaluation_id,
                "task_index":       t["task_index"],
                "task_description": t["task_description"],
                "score":            t["score"],
            }
            for t in scores
        ]

        payload = {
            "evaluation_id": evaluation_id,
            "apprentice_id": apprentice_info["employee_id"],
            "course_id": selected_task,
            "task_name": selected_task,
            "evaluator_name": evaluator_name,
            "evaluator_emp_id": evaluator_emp_id,
            "evaluation_date": evaluation_date.isoformat(),
            "evaluation_type": evaluation_type,
            "actual_duration": duration_seconds,
            "form_version": form_version,
            "result": result,
            "comments": merged_comments,
            "submitted_by": evaluator_emp_id,
            "submitted_at": datetime.now(timezone.utc).isoformat(),
            "ident": None,
            "performance_objective": None,
        }
        _submit_evaluation(payload, task_rows)


main()