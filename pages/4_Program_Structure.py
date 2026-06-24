"""Program Structure page — read-only map of the Transmission apprenticeship program.
"""
import sys
import os
import re
import logging
from pathlib import Path
from html import escape

sys.path.insert(0, str(Path(__file__).parent.parent))

import pandas as pd
import streamlit as st
import pypdfium2 as pdfium
from google.api_core.exceptions import Forbidden, NotFound

from app.components.navigation import require_auth, render_sidebar
from app.core.rbac import has_role, ROLE_ADMIN, ROLE_SUPERVISOR, ROLE_AUDITOR
from app.core.config import get_config
from app.services.bigquery_service import (
    fetch_program_structure,
    fetch_evaluation_codes,
    fetch_completed_evaluations,
    fetch_evaluation_by_id,
    fetch_communication_log,
)
from app.services.gcs_service import list_files_in_gcs_folder, download_file_from_gcs
from app.services.pdf_service import generate_jpm_pdf
from app.utils.formatters import format_date

logger = logging.getLogger(__name__)

_FORM_BADGE_CLASS = {"JPM": "badge-jpm", "HOSD": "badge-hosd"}


# ── Styles ────────────────────────────────────────────────────────────────────

def _inject_styles() -> None:
    st.markdown(
        """
        <style>
        .section-header {
            font-size: 1.1rem;
            font-weight: 700;
            color: #e2e8f0;
            margin: 1.5rem 0 0.25rem 0;
        }
        .topic-desc {
            color: #a0aec0;
            font-size: 0.85rem;
            margin: 0 0 0.6rem 0;
        }
        .group-label {
            font-size: 0.72rem;
            font-weight: 700;
            color: #cbd5e0;
            letter-spacing: 0.06em;
            text-transform: uppercase;
            border-left: 3px solid #4299e1;
            padding-left: 0.55rem;
            margin: 0.7rem 0 0.35rem 0;
        }
        .activity-item {
            color: #e2e8f0;
            font-size: 0.9rem;
            padding: 0.1rem 0 0.1rem 0.55rem;
        }
        .form-row {
            display: flex;
            align-items: center;
            gap: 0.5rem;
            padding: 0.18rem 0 0.18rem 0.55rem;
            font-size: 0.9rem;
            color: #e2e8f0;
        }
        .badge {
            font-size: 0.66rem;
            font-weight: 700;
            letter-spacing: 0.04em;
            padding: 0.1rem 0.5rem;
            border-radius: 10px;
        }
        .badge-jpm  { background: #2c5282; color: #bee3f8; }
        .badge-hosd { background: #553c9a; color: #e9d8fd; }
        .badge-ver  { background: #2d3748; color: #a0aec0; }
        .badge-active   { background: #276749; color: #c6f6d5; }
        .badge-inactive { background: #4a5568; color: #e2e8f0; }
        .empty-note { color: #4a5568; font-size: 0.85rem; font-style: italic; padding-left: 0.55rem; }
        .form-field-label { font-size: 0.72rem; color: #a0aec0; margin-bottom: 0.05rem; text-transform: uppercase; letter-spacing: 0.04em; }
        .form-field-value { font-size: 0.92rem; color: #e2e8f0; margin-bottom: 0.65rem; font-weight: 500; }
        .section-divider { border-top: 1px solid #2d3748; margin: 0.8rem 0; }
        .result-pass { background: #276749; color: #f0fff4; padding: 0.3rem 0.8rem; border-radius: 6px; display: inline-block; font-weight: 700; }
        .result-fail { background: #9b2c2c; color: #fff5f5; padding: 0.3rem 0.8rem; border-radius: 6px; display: inline-block; font-weight: 700; }
        .placeholder-box {
            background: #1e2130;
            border-radius: 12px;
            padding: 2.5rem;
            text-align: center;
            color: #718096;
            border: 1px dashed #2d3748;
            min-height: 220px;
            display: flex;
            align-items: center;
            justify-content: center;
            margin-top: 1rem;
        }
        </style>
        """,
        unsafe_allow_html=True,
    )


# ── Structure-tab rendering (real data: Evaluation_Questions) ────────────────

@st.cache_data(ttl=3600, show_spinner="Loading program structure…")
def _load_program_structure() -> list[dict]:
    try:
        return fetch_program_structure()
    except Exception as e:
        logger.error("Failed to load program structure: %s", e)
        return []


def _nest_structure(rows: list[dict]) -> dict:
    """Nest flat rows into Topic → {code: {type, objectives: {objective: [questions]}}}."""
    topics: dict = {}
    for r in rows:
        topic = _clean_title(r.get("topic"))
        code = r.get("code") or "—"
        ftype = (r.get("type") or "").upper()
        objective = r.get("objective") or "General"
        question = r.get("question")

        forms = topics.setdefault(topic, {})
        form = forms.setdefault(code, {"type": ftype, "objectives": {}})
        questions = form["objectives"].setdefault(objective, [])
        if question and question not in questions:
            questions.append(question)
    return topics


def _structure_matches_search(topic: str, forms: dict, query: str) -> bool:
    """True if the query appears in the topic, a form code, an objective, or a question."""
    if not query:
        return True
    q = query.lower()
    if q in topic.lower():
        return True
    for code, form in forms.items():
        if q in code.lower():
            return True
        for objective, questions in form["objectives"].items():
            if q in objective.lower() or any(q in (qq or "").lower() for qq in questions):
                return True
    return False


def _filter_forms_by_type(forms: dict, form_type: str) -> dict:
    if form_type == "All":
        return forms
    return {code: f for code, f in forms.items() if f["type"] == form_type}


def _render_structure_topic(topic: str, forms: dict) -> None:
    label = f"{topic}  ({len(forms)} form{'s' if len(forms) != 1 else ''})"
    with st.expander(label, expanded=False):
        for code, form in sorted(forms.items()):
            badge_class = _FORM_BADGE_CLASS.get(form["type"], "badge-ver")
            with st.container(border=True):
                st.markdown(
                    f'<div class="form-row">'
                    f'<span class="badge {badge_class}">{escape(form["type"] or "—")}</span>'
                    f'<span><strong>{escape(code)}</strong></span>'
                    f'</div>',
                    unsafe_allow_html=True,
                )
                for objective, questions in form["objectives"].items():
                    st.markdown(
                        f'<div class="group-label">📋 {escape(objective)}</div>',
                        unsafe_allow_html=True,
                    )
                    if not questions:
                        st.markdown('<div class="empty-note">No questions defined.</div>', unsafe_allow_html=True)
                    for q in questions:
                        st.markdown(f'<div class="activity-item">• {escape(q)}</div>', unsafe_allow_html=True)


def _render_structure_tab() -> None:
    st.markdown(
        '<div class="section-header">🗺️ Program Structure — Transmission</div>',
        unsafe_allow_html=True,
    )
    st.caption(
        "Read-only map from evaluation definitions: "
        "Topic → JPM / HOSD Form → Task Objective → Question."
    )

    rows = _load_program_structure()
    if not rows:
        st.info("No program structure data found.")
        return

    structure = _nest_structure(rows)
    topics_list = sorted(structure.keys())

    # ── Filters ────────────────────────────────────────────────────────────
    f1, f2, f3 = st.columns([1.8, 1, 1.6])
    with f1:
        topic_filter = st.selectbox("Topic", ["All Topics"] + topics_list)
    with f2:
        type_filter = st.selectbox("Form Type", ["All", "JPM", "HOSD"])
    with f3:
        search = st.text_input("Search", placeholder="Search topics, forms, objectives, questions…")

    # ── Render ──────────────────────────────────────────────────────────────
    shown = 0
    for topic in topics_list:
        if topic_filter not in ("All Topics", topic):
            continue
        forms = _filter_forms_by_type(structure[topic], type_filter)
        if not forms:
            continue
        if not _structure_matches_search(topic, forms, search):
            continue
        shown += 1
        _render_structure_topic(topic, forms)

    if shown == 0:
        st.info("No topics match the current filters.")


# ═════════════════════════════════════════════════════════════════════════════
# FORM TEMPLATES TAB  — BigQuery Evaluation_Questions → GCS PDFs
# ═════════════════════════════════════════════════════════════════════════════

def _norm(text: str | None) -> str:
    """Normalize for matching: lowercase, non-alphanumerics → single space.

    Mirrors the normalizer on the JPM & HOSD page so code↔filename matching is
    identical across both pages.
    """
    return re.sub(r"[^a-z0-9]+", " ", (text or "").lower()).strip()


def _clean_title(title: str | None) -> str:
    """Strip a trailing document extension from an evaluation title.

    Some Evaluation_Title values in the source are stored as filenames
    (e.g. 'Installing Protective Grounds.pdf'); show the clean title instead.
    """
    t = (title or "").strip()
    return re.sub(r"(?i)\.(pdf|docx?|xlsx?)$", "", t).strip() or "—"


def _infer_form_type(code: str, declared: str | None) -> str:
    """Form type from the table's Evaluation_Type, falling back to the code text."""
    if declared:
        return declared.upper()
    upper = (code or "").upper()
    if "HOSD" in upper:
        return "HOSD"
    if "JPM" in upper:
        return "JPM"
    return "—"


@st.cache_data(ttl=3600, show_spinner=False)
def _load_evaluation_forms() -> list[dict]:
    """Distinct {evaluation_code, evaluation_type, evaluation_title} from BigQuery."""
    try:
        return fetch_evaluation_codes()
    except Exception as e:
        logger.error("Failed to load evaluation codes: %s", e)
        return []


@st.cache_data(ttl=60, show_spinner=False)
def _list_form_pdfs(bucket: str) -> list[str]:
    try:
        return list_files_in_gcs_folder(bucket)
    except Exception as e:
        logger.error("Failed to list GCS form PDFs: %s", e)
        return []


@st.cache_data(ttl=300, show_spinner=False)
def _download_form_pdf(bucket: str, filename: str) -> bytes:
    return download_file_from_gcs(bucket, filename)


def _match_pdf_for_code(code: str, filenames: list[str]) -> str | None:
    """Find the GCS filename whose stem matches an Evaluation_Code.

    Files are named 'CODE - Title.pdf', so the normalized code is an exact match
    or a prefix/substring of the normalized filename stem. Inverse of the JPM &
    HOSD page's filename→code resolver. Prefers exact, then prefix, then
    substring; deterministic via sorted filenames.
    """
    code_norm = _norm(code)
    if not code_norm:
        return None

    exact = prefix = contains = None
    for fn in sorted(filenames):
        stem_norm = _norm(fn.rsplit(".", 1)[0])
        if stem_norm == code_norm and exact is None:
            exact = fn
        elif stem_norm.startswith(code_norm) and prefix is None:
            prefix = fn
        elif code_norm in stem_norm and contains is None:
            contains = fn
    return exact or prefix or contains


def _safe_download(bucket: str, filename: str) -> tuple[bytes | None, str | None]:
    """Download a PDF, converting cloud errors into clear, user-facing messages."""
    try:
        return _download_form_pdf(bucket, filename), None
    except Forbidden:
        return None, "Permission denied loading this PDF. Contact your administrator."
    except NotFound:
        return None, "This PDF is no longer available in storage."
    except Exception as e:
        logger.error("Failed to download %s: %s", filename, e)
        return None, "Could not load this PDF. Please try again later."


def _render_pdf_preview(pdf_bytes: bytes) -> None:
    """Render the first page of a PDF as an image."""
    try:
        pdf = pdfium.PdfDocument(pdf_bytes)
        page = pdf[0]
        image = page.render(scale=2).to_pil()
        st.image(image, use_container_width=True)
    except Exception as e:
        logger.error("Could not render PDF preview: %s", e)
        st.error("Could not render this PDF — the file may be invalid or corrupt.")


def _render_form_row(bucket: str, form: dict, filenames: list[str]) -> None:
    code = form.get("evaluation_code") or "—"
    title = _clean_title(form.get("evaluation_title"))
    ftype = _infer_form_type(code, form.get("evaluation_type"))
    badge_class = _FORM_BADGE_CLASS.get(ftype, "badge-ver")

    with st.container(border=True):
        st.markdown(
            f'<div class="form-row">'
            f'<span class="badge {badge_class}">{escape(ftype)}</span>'
            f'<span><strong>{escape(code)}</strong></span>'
            f'</div>'
            f'<div class="topic-desc">{escape(title)}</div>',
            unsafe_allow_html=True,
        )

        filename = _match_pdf_for_code(code, filenames)
        if not filename:
            st.warning("Template PDF not available in storage.")
            return

        pdf_bytes, err = _safe_download(bucket, filename)
        if err:
            st.error(err)
            return

        view_key = f"ft_view_{code}"
        c1, c2, _ = st.columns([1, 1, 3])
        with c1:
            if st.button("👁 View PDF", key=f"ft_btn_{code}", use_container_width=True):
                st.session_state[view_key] = not st.session_state.get(view_key, False)
        with c2:
            st.download_button(
                "📥 Download PDF",
                data=pdf_bytes,
                file_name=filename,
                mime="application/pdf",
                key=f"ft_dl_{code}",
                use_container_width=True,
            )

        if st.session_state.get(view_key):
            with st.container(border=True):
                _render_pdf_preview(pdf_bytes)


def _render_form_templates_tab(bucket: str) -> None:
    st.markdown(
        '<div class="section-header">🗂️ Form Templates — JPM / HOSD</div>',
        unsafe_allow_html=True,
    )
    st.caption(
        "Select a topic to see its linked JPM / HOSD forms. Templates are read "
        "from cloud storage for read-only preview and download."
    )

    forms = _load_evaluation_forms()
    if not forms:
        st.info("No evaluation forms found. Please contact your administrator.")
        return

    titles = sorted({_clean_title(f["evaluation_title"]) for f in forms if f.get("evaluation_title")})
    if not titles:
        st.info("No evaluation titles available to display.")
        return

    selected = st.selectbox(
        "Topic / Evaluation Title",
        options=["— Select a topic —"] + titles,
        key="ft_topic",
    )
    if selected == "— Select a topic —":
        st.info("Select a topic above to view its linked forms.")
        return

    linked = [f for f in forms if _clean_title(f.get("evaluation_title")) == selected]
    st.markdown(
        f'<div class="section-header">📄 {escape(selected)}'
        f' &nbsp;<span class="badge badge-ver">{len(linked)} form(s)</span></div>',
        unsafe_allow_html=True,
    )

    filenames = _list_form_pdfs(bucket)
    if not filenames:
        st.warning("No form templates are currently available in storage.")

    for form in linked:
        _render_form_row(bucket, form, filenames)


# ═════════════════════════════════════════════════════════════════════════════
# COMPLETED DOCUMENTATION TAB — read-only completed evaluation records
# ═════════════════════════════════════════════════════════════════════════════

@st.cache_data(ttl=600, show_spinner="Loading completed records…")
def _load_completed_docs(supervisor_name: str | None) -> list[dict]:
    try:
        return fetch_completed_evaluations(supervisor_name)
    except Exception as e:
        logger.error("Failed to load completed evaluations: %s", e)
        return []


@st.cache_data(ttl=600, show_spinner=False)
def _load_evaluation(evaluation_id: str) -> dict | None:
    try:
        return fetch_evaluation_by_id(evaluation_id)
    except Exception as e:
        logger.error("Failed to load evaluation %s: %s", evaluation_id, e)
        return None


def _topic_for_task(task_name: str | None, forms: list[dict]) -> str:
    """Best-effort topic for a completed record by matching its form/task name
    to an Evaluation_Title (or code). Fuzzy — may not resolve every record."""
    tn = _norm(task_name)
    if not tn:
        return "—"
    best, best_len = "—", -1
    for f in forms:
        title = f.get("evaluation_title") or ""
        for key in (_norm(f.get("evaluation_code")), _norm(title)):
            if key and (key in tn or tn in key) and len(key) > best_len:
                best, best_len = _clean_title(title), len(key)
    return best


def _pdf_payload_from_evaluation(ev: dict) -> tuple[dict, list[dict]]:
    """Map a stored evaluation row to the shape generate_jpm_pdf() expects."""
    eval_row = {
        "course_name":           ev.get("task_name") or "JPM Evaluation",
        "apprentice_id":         ev.get("apprentice_id"),
        "course_id":             ev.get("course_id"),
        "observer_name":         ev.get("evaluator_name"),
        "observer_emp_id":       ev.get("evaluator_emp_id"),
        "evaluation_date":       str(ev.get("evaluation_date") or "—"),
        "performance_objective": ev.get("performance_objective"),
        "result":                ev.get("result"),
        "comments":              ev.get("comments"),
        "submitted_by":          ev.get("submitted_by"),
        "submitted_at":          str(ev.get("submitted_at") or "—"),
    }
    return eval_row, ev.get("tasks", [])


def _field(label: str, value) -> None:
    st.markdown(
        f'<div class="form-field-label">{escape(label)}</div>'
        f'<div class="form-field-value">{escape(str(value if value not in (None, "") else "—"))}</div>',
        unsafe_allow_html=True,
    )


def _render_completed_record(ev: dict) -> None:
    c1, c2, c3 = st.columns(3)
    with c1:
        _field("Apprentice ID", ev.get("apprentice_id"))
    with c2:
        _field("Form / Activity", ev.get("task_name"))
    with c3:
        _field("Date", str(ev.get("evaluation_date") or "—"))

    c1, c2, c3 = st.columns(3)
    with c1:
        _field("Observer", ev.get("evaluator_name"))
    with c2:
        _field("Type", ev.get("evaluation_type"))
    with c3:
        _field("Form Version", ev.get("form_version"))

    st.markdown('<div class="section-divider"></div>', unsafe_allow_html=True)
    st.markdown("**Task Scores**")
    tasks = ev.get("tasks", [])
    if tasks:
        task_df = pd.DataFrame(tasks)[["task_index", "task_description", "score"]]
        task_df.columns = ["#", "Task Description", "Score (1–5)"]
        st.dataframe(task_df, use_container_width=True, hide_index=True)
    else:
        st.info("No task scores recorded for this evaluation.")

    st.markdown('<div class="section-divider"></div>', unsafe_allow_html=True)
    result = (ev.get("result") or "").upper()
    if result == "PASS":
        st.markdown('<span class="result-pass">✅ PASS</span>', unsafe_allow_html=True)
    elif result == "FAIL":
        st.markdown('<span class="result-fail">❌ FAIL</span>', unsafe_allow_html=True)
    else:
        st.caption("Result: —")

    if ev.get("comments"):
        st.markdown("<br>", unsafe_allow_html=True)
        _field("Comments", ev.get("comments"))

    # Download the completed record as a PDF (generated on the fly, read-only).
    try:
        eval_row, task_rows = _pdf_payload_from_evaluation(ev)
        pdf_bytes = generate_jpm_pdf(eval_row, task_rows)
        safe_name = re.sub(r"[^A-Za-z0-9]+", "_", (ev.get("task_name") or "record")).strip("_")
        st.download_button(
            "📥 Download Record PDF",
            data=pdf_bytes,
            file_name=f"{safe_name}_{ev.get('apprentice_id', '')}.pdf",
            mime="application/pdf",
            key=f"cd_dl_{ev.get('evaluation_id')}",
        )
    except Exception as e:
        logger.error("Failed to generate record PDF: %s", e)
        st.warning("Could not generate a PDF for this record.")


def _render_completed_docs_tab(supervisor_name: str | None) -> None:
    st.markdown(
        '<div class="section-header">✅ Completed Documentation</div>',
        unsafe_allow_html=True,
    )
    st.caption(
        "Read-only completed evaluation records. Evaluations are entered on the "
        "JPM & HOSD page."
    )

    records = _load_completed_docs(supervisor_name)
    if not records:
        st.info("No completed evaluation records found.")
        return

    forms = _load_evaluation_forms()  # for best-effort topic derivation
    df = pd.DataFrame(records)
    df["topic"] = df["task_name"].apply(lambda t: _topic_for_task(t, forms))
    df["eval_date"] = pd.to_datetime(df["evaluation_date"], errors="coerce")

    # ── Filters ──────────────────────────────────────────────────────────
    f1, f2, f3 = st.columns([1.4, 1.4, 1])
    with f1:
        employees = ["All"] + sorted(df["employee_name"].dropna().unique().tolist())
        sel_emp = st.selectbox("Employee", employees, key="cd_emp")
    with f2:
        topics = ["All"] + sorted([t for t in df["topic"].unique().tolist() if t and t != "—"])
        sel_topic = st.selectbox("Topic (best-effort)", topics, key="cd_topic")
    with f3:
        sel_status = st.selectbox("Status", ["All", "PASS", "FAIL"], key="cd_status")

    valid_dates = df["eval_date"].dropna()
    d1, d2 = st.columns(2)
    if not valid_dates.empty:
        min_d, max_d = valid_dates.min().date(), valid_dates.max().date()
        with d1:
            date_from = st.date_input("From", value=min_d, min_value=min_d, max_value=max_d, key="cd_from")
        with d2:
            date_to = st.date_input("To", value=max_d, min_value=min_d, max_value=max_d, key="cd_to")
    else:
        date_from = date_to = None

    search = st.text_input("Search", placeholder="Search employee or form / activity…", key="cd_search")

    # ── Apply filters ────────────────────────────────────────────────────
    fdf = df.copy()
    if sel_emp != "All":
        fdf = fdf[fdf["employee_name"] == sel_emp]
    if sel_topic != "All":
        fdf = fdf[fdf["topic"] == sel_topic]
    if sel_status != "All":
        fdf = fdf[fdf["result"].fillna("").str.upper() == sel_status]
    if date_from and date_to:
        ed = fdf["eval_date"].dt.date
        fdf = fdf[ed.notna() & (ed >= date_from) & (ed <= date_to)]
    if search:
        q = search.lower()
        fdf = fdf[
            fdf["employee_name"].fillna("").str.lower().str.contains(q)
            | fdf["task_name"].fillna("").str.lower().str.contains(q)
        ]

    if fdf.empty:
        st.info("No records match the current filters.")
        return

    # ── Table ────────────────────────────────────────────────────────────
    table = fdf.copy()
    table["Score"] = table["avg_score"].apply(lambda v: f"{v:.1f}" if pd.notna(v) else "—")
    table["Status"] = table["result"].fillna("").str.upper().map(
        {"PASS": "🟢 PASS", "FAIL": "🔴 FAIL"}
    ).fillna(table["result"])
    table["Completion Date"] = table["eval_date"].apply(
        lambda d: format_date(d.date()) if pd.notna(d) else "—"
    )
    display = table[[
        "employee_name", "topic", "task_name", "Score", "Status",
        "Completion Date", "evaluator_name",
    ]].rename(columns={
        "employee_name": "Employee",
        "topic": "Topic",
        "task_name": "Activity / Form",
        "evaluator_name": "Observer",
    })
    st.dataframe(display, use_container_width=True, hide_index=True)
    st.caption(f"{len(fdf)} completed record(s).")

    # ── Drill into one record ────────────────────────────────────────────
    st.markdown('<div class="section-divider"></div>', unsafe_allow_html=True)
    st.markdown("#### View a completed record")

    label_map = {
        f'{format_date(r["eval_date"].date()) if pd.notna(r["eval_date"]) else "—"}'
        f' | {r["employee_name"] or r["apprentice_id"]} | {r["task_name"]} '
        f'| {(r["result"] or "—").upper()}': r["evaluation_id"]
        for _, r in fdf.iterrows()
    }
    selected_label = st.selectbox(
        "Select a record",
        options=["— Select a record —"] + list(label_map.keys()),
        key="cd_record",
    )
    if selected_label == "— Select a record —":
        return

    ev = _load_evaluation(label_map[selected_label])
    if not ev:
        st.error("Could not load this record. Please try again later.")
        return

    with st.container(border=True):
        _render_completed_record(ev)


# ═════════════════════════════════════════════════════════════════════════════
# COMMUNICATION TEMPLATES TAB — code-defined templates + real sent history
#
# Template definitions live in code (only implemented templates are listed).
# Each template's `email_type` keys into the real `communication_log` table for
# its sent history. Active/inactive is driven by EMAIL_ENABLED. This page is
# read-only — emails are sent from the JPM & HOSD page on submit.
# ═════════════════════════════════════════════════════════════════════════════

# Only templates that are actually implemented. `email_type` must match the
# value written to communication_log by the sender (see pages/6_JPM_HOSD.py).
_COMM_TEMPLATES: list[dict] = [
    {
        "name": "JPM / HOSD Evaluation Confirmation",
        "email_type": "JPM_HOSD_CONFIRMATION",
        "trigger": "Sent automatically when a JPM / HOSD evaluation is submitted.",
        "recipients": ["Apprentice", "Supervisor"],
        "subject": "JPM / HOSD evaluation confirmation for {apprentice_name}",
        "body": (
            "Sent to the apprentice and their supervisor summarizing the submitted "
            "evaluation — form title, result (PASS / FAIL), evaluator, and date.\n\n"
            "The exact subject and body are generated at send time on the "
            "JPM & HOSD page."
        ),
    },
]


def _email_enabled() -> bool:
    """Whether real email sending is on (EMAIL_ENABLED). Mirrors email_service."""
    return os.getenv("EMAIL_ENABLED", "false").strip().lower() in ("1", "true", "yes", "on")


@st.cache_data(ttl=120, show_spinner=False)
def _load_comm_log(email_type: str | None) -> list[dict]:
    try:
        return fetch_communication_log(email_type)
    except Exception as e:
        logger.error("Failed to load communication log (%s): %s", email_type, e)
        return []


def _render_comm_history(email_type: str | None) -> None:
    rows = _load_comm_log(email_type)
    if not rows:
        st.markdown('<div class="empty-note">No emails sent yet.</div>', unsafe_allow_html=True)
        return

    df = pd.DataFrame(rows)
    when = pd.to_datetime(df["created_at"], errors="coerce").dt.strftime("%Y-%m-%d %H:%M")
    status_icon = {"SENT": "🟢 SENT", "FAILED": "🔴 FAILED", "SKIPPED": "⚪ SKIPPED"}
    display = pd.DataFrame({
        "When":      when.fillna("—"),
        "Apprentice": df["apprentice_id"].fillna("—"),
        "Recipient":  df["recipient_type"].fillna("—"),
        "Email":      df["recipient_email"].fillna("—"),
        "Status":     df["status"].map(status_icon).fillna(df["status"]),
    })
    st.dataframe(display, use_container_width=True, hide_index=True)
    st.caption(f"{len(df)} attempt(s) logged.")


def _render_comm_template(tpl: dict, is_active: bool) -> None:
    badge_class = "badge-active" if is_active else "badge-inactive"
    status_text = "● Active" if is_active else "○ Inactive"

    with st.expander(tpl["name"], expanded=False):
        st.markdown(
            f'<span class="badge {badge_class}">{status_text}</span>',
            unsafe_allow_html=True,
        )

        st.markdown('<div class="group-label">⚡ Trigger Condition</div>', unsafe_allow_html=True)
        st.markdown(
            f'<div class="activity-item">{escape(tpl.get("trigger", "—"))}</div>',
            unsafe_allow_html=True,
        )

        st.markdown('<div class="group-label">👥 Recipients</div>', unsafe_allow_html=True)
        recipients = tpl.get("recipients", [])
        st.markdown(
            f'<div class="activity-item">{escape(", ".join(recipients) or "—")}</div>',
            unsafe_allow_html=True,
        )

        st.markdown('<div class="group-label">✉️ Email Subject</div>', unsafe_allow_html=True)
        st.markdown(
            f'<div class="form-field-value">{escape(tpl.get("subject", "—"))}</div>',
            unsafe_allow_html=True,
        )

        st.markdown('<div class="group-label">📧 Email Body</div>', unsafe_allow_html=True)
        st.code(tpl.get("body", ""), language=None)

        st.markdown('<div class="group-label">📜 Sent History</div>', unsafe_allow_html=True)
        _render_comm_history(tpl.get("email_type"))


def _render_comm_templates_tab() -> None:
    st.markdown(
        '<div class="section-header">✉️ Communication Templates</div>',
        unsafe_allow_html=True,
    )
    st.caption(
        "Read-only reference for program email templates, their trigger conditions, "
        "and real sent history. Emails are sent from the JPM & HOSD page."
    )

    enabled = _email_enabled()
    if not enabled:
        st.info(
            "Email sending is currently **disabled** (EMAIL_ENABLED is off), so "
            "templates show as Inactive. History below still reflects logged attempts."
        )

    status_filter = st.selectbox("Status", ["All", "Active", "Inactive"], key="ct_status")

    shown = 0
    for tpl in _COMM_TEMPLATES:
        # All implemented templates are gated by the global EMAIL_ENABLED switch.
        is_active = enabled
        if status_filter == "Active" and not is_active:
            continue
        if status_filter == "Inactive" and is_active:
            continue
        _render_comm_template(tpl, is_active)
        shown += 1

    if shown == 0:
        st.info("No communication templates match the current filter.")


# ── Page entry point ─────────────────────────────────────────────────────────

def main() -> None:
    auth = require_auth()
    user_info = render_sidebar(auth)

    if not any(has_role(auth, r) for r in [ROLE_SUPERVISOR, ROLE_ADMIN, ROLE_AUDITOR]):
        st.error("🚫 Access Denied — This page is restricted to supervisors, admins, and auditors.")
        st.stop()

    _inject_styles()
    st.title("Program Structure")
    st.markdown("---")

    bucket = get_config().get("GCS_BUCKET")

    # Supervisors (not admins/auditors) see only the records they evaluated.
    is_supervisor_only = (
        has_role(auth, ROLE_SUPERVISOR)
        and not has_role(auth, ROLE_ADMIN)
        and not has_role(auth, ROLE_AUDITOR)
    )
    supervisor_name_filter = (
        ((user_info.get("displayName") or "").strip() or None)
        if is_supervisor_only else None
    )

    tab_structure, tab_forms, tab_completed, tab_comms = st.tabs([
        "Structure",
        "Form Templates",
        "Completed Documentation",
        "Communication Templates",
    ])

    with tab_structure:
        _render_structure_tab()

    with tab_forms:
        if not bucket:
            st.error("❌ Storage is not configured (GCS_BUCKET). Contact your administrator.")
        else:
            _render_form_templates_tab(bucket)

    with tab_completed:
        _render_completed_docs_tab(supervisor_name_filter)

    with tab_comms:
        _render_comm_templates_tab()


main()
