"""PDF generation service for JPM evaluation records."""
from io import BytesIO

from reportlab.lib.pagesizes import LETTER
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.units import inch
from reportlab.lib import colors
from reportlab.platypus import (
    SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle, HRFlowable
)
from reportlab.lib.enums import TA_CENTER, TA_LEFT


_PASS_GREEN = colors.HexColor("#1e7e34")
_FAIL_RED   = colors.HexColor("#bd2130")
_HEADER_BG  = colors.HexColor("#2c3e50")
_ROW_ALT    = colors.HexColor("#f2f2f2")
_BORDER     = colors.HexColor("#555555")


def generate_jpm_pdf(evaluation_row: dict, task_rows: list[dict]) -> bytes:
    """
    Build a JPM Evaluation PDF from the validated payload.
    Returns raw PDF bytes.
    """
    buffer = BytesIO()
    doc = SimpleDocTemplate(
        buffer,
        pagesize=LETTER,
        leftMargin=0.75 * inch,
        rightMargin=0.75 * inch,
        topMargin=0.75 * inch,
        bottomMargin=0.75 * inch,
    )

    styles = getSampleStyleSheet()
    story  = []

    # ── Custom styles ──────────────────────────────────────────────────
    title_style = ParagraphStyle(
        "title",
        parent=styles["Normal"],
        fontSize=16,
        fontName="Helvetica-Bold",
        alignment=TA_CENTER,
        spaceAfter=4,
    )
    subtitle_style = ParagraphStyle(
        "subtitle",
        parent=styles["Normal"],
        fontSize=10,
        fontName="Helvetica",
        alignment=TA_CENTER,
        spaceAfter=12,
        textColor=colors.grey,
    )
    section_label_style = ParagraphStyle(
        "section_label",
        parent=styles["Normal"],
        fontSize=9,
        fontName="Helvetica-Bold",
        textColor=colors.white,
        alignment=TA_LEFT,
    )
    field_label_style = ParagraphStyle(
        "field_label",
        parent=styles["Normal"],
        fontSize=8,
        fontName="Helvetica-Bold",
        textColor=colors.HexColor("#555555"),
    )
    field_value_style = ParagraphStyle(
        "field_value",
        parent=styles["Normal"],
        fontSize=9,
        fontName="Helvetica",
    )
    checkbox_style = ParagraphStyle(
        "checkbox",
        parent=styles["Normal"],
        fontSize=9,
        fontName="Helvetica",
    )
    objective_style = ParagraphStyle(
        "objective",
        parent=styles["Normal"],
        fontSize=9,
        fontName="Helvetica",
        leading=13,
    )
    result_style_pass = ParagraphStyle(
        "result_pass",
        parent=styles["Normal"],
        fontSize=18,
        fontName="Helvetica-Bold",
        textColor=_PASS_GREEN,
        alignment=TA_CENTER,
        spaceBefore=4,
        spaceAfter=4,
    )
    result_style_fail = ParagraphStyle(
        "result_fail",
        parent=styles["Normal"],
        fontSize=18,
        fontName="Helvetica-Bold",
        textColor=_FAIL_RED,
        alignment=TA_CENTER,
        spaceBefore=4,
        spaceAfter=4,
    )
    footer_style = ParagraphStyle(
        "footer",
        parent=styles["Normal"],
        fontSize=7,
        fontName="Helvetica",
        textColor=colors.grey,
        alignment=TA_CENTER,
    )

    usable_width = doc.width

    def _section_header(text: str):
        """Render a dark banner section header."""
        return Table(
            [[Paragraph(text, section_label_style)]],
            colWidths=[usable_width],
            style=TableStyle([
                ("BACKGROUND",    (0, 0), (-1, -1), _HEADER_BG),
                ("TOPPADDING",    (0, 0), (-1, -1), 5),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 5),
                ("LEFTPADDING",   (0, 0), (-1, -1), 8),
            ]),
        )

    # ── Title: course name as main title ───────────────────────────────
    course_name = evaluation_row.get("course_name") or "JPM Evaluation"
    story.append(Paragraph(course_name.upper(), title_style))
    story.append(Paragraph("Job Performance Measure — Evaluation Record", subtitle_style))
    story.append(HRFlowable(width="100%", thickness=1, color=_BORDER))
    story.append(Spacer(1, 10))

    # ── Evaluation Information ─────────────────────────────────────────
    story.append(_section_header("EVALUATION INFORMATION"))
    story.append(Spacer(1, 6))

    # Apprentice ID / Course ID row
    id_data = [
        [
            Paragraph("APPRENTICE ID", field_label_style),
            Paragraph("COURSE ID",     field_label_style),
        ],
        [
            Paragraph(evaluation_row.get("apprentice_id", "—"), field_value_style),
            Paragraph(evaluation_row.get("course_id",     "—"), field_value_style),
        ],
    ]
    id_table = Table(id_data, colWidths=[usable_width / 2] * 2)
    id_table.setStyle(TableStyle([
        ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
        ("TOPPADDING",    (0, 0), (-1, -1), 2),
        ("LINEBELOW",     (0, 0), (-1, 0),  0.5, colors.HexColor("#cccccc")),
    ]))
    story.append(id_table)
    story.append(Spacer(1, 8))

    # Trainee / Observer / Date / Initial+Retake
    eval_date_str = evaluation_row.get("evaluation_date", "—")

    # Checkbox rendering: ☑ checked  ☐ unchecked
    is_initial    = evaluation_row.get("is_initial", False)
    is_retake     = evaluation_row.get("is_retake",  False)
    initial_box   = "☑ Initial" if is_initial else "☐ Initial"
    retake_box    = "☑ Retake"  if is_retake  else "☐ Retake"
    checkbox_text = f"{initial_box}     {retake_box}"

    header_data = [
        [
            Paragraph("TRAINEE",  field_label_style),
            Paragraph("EMP ID",   field_label_style),
            Paragraph("OBSERVER", field_label_style),
            Paragraph("EMP ID",   field_label_style),
        ],
        [
            Paragraph(evaluation_row.get("trainee_name",    "—"), field_value_style),
            Paragraph(evaluation_row.get("trainee_emp_id",  "—"), field_value_style),
            Paragraph(evaluation_row.get("observer_name",   "—"), field_value_style),
            Paragraph(evaluation_row.get("observer_emp_id", "—"), field_value_style),
        ],
        [
            Paragraph("DATE",               field_label_style),
            Paragraph("EVALUATION TYPE",    field_label_style),
            Paragraph("",                   field_label_style),
            Paragraph("",                   field_label_style),
        ],
        [
            Paragraph(eval_date_str,  field_value_style),
            Paragraph(checkbox_text,  checkbox_style),
            Paragraph("",             field_value_style),
            Paragraph("",             field_value_style),
        ],
    ]
    col_w = usable_width / 4
    header_table = Table(header_data, colWidths=[col_w] * 4)
    header_table.setStyle(TableStyle([
        ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
        ("TOPPADDING",    (0, 0), (-1, -1), 2),
        ("LINEBELOW",     (0, 0), (-1, 1),  0.5, colors.HexColor("#cccccc")),
    ]))
    story.append(header_table)
    story.append(Spacer(1, 10))

    # ── Performance Objective ──────────────────────────────────────────
    story.append(_section_header("PERFORMANCE OBJECTIVE"))
    story.append(Spacer(1, 6))
    obj_text = evaluation_row.get("performance_objective") or "—"
    story.append(Paragraph(obj_text, objective_style))
    story.append(Spacer(1, 10))

    # ── Task Table ─────────────────────────────────────────────────────
    story.append(_section_header("TASKS"))
    story.append(Spacer(1, 6))

    task_header = [
        Paragraph("#",                section_label_style),
        Paragraph("Task Description", section_label_style),
        Paragraph("Score",            section_label_style),
        Paragraph("Result",           section_label_style),
    ]
    task_data = [task_header]

    for row in task_rows:
        score     = row.get("score", 0)
        pass_fail = "PASS" if score >= 3 else "FAIL"
        pf_color  = _PASS_GREEN if score >= 3 else _FAIL_RED
        pf_style  = ParagraphStyle(
            f"pf_{row.get('task_index')}",
            parent=styles["Normal"],
            fontSize=8,
            fontName="Helvetica-Bold",
            textColor=pf_color,
        )
        task_data.append([
            Paragraph(str(row.get("task_index", "")),  field_value_style),
            Paragraph(row.get("task_description", ""), field_value_style),
            Paragraph(str(score),                      field_value_style),
            Paragraph(pass_fail,                       pf_style),
        ])

    col_widths = [
        0.4  * inch,
        usable_width - 0.4 * inch - 0.7 * inch - 0.7 * inch,
        0.7  * inch,
        0.7  * inch,
    ]
    task_table = Table(task_data, colWidths=col_widths, repeatRows=1)
    task_style = [
        ("BACKGROUND",    (0, 0), (-1, 0),  _HEADER_BG),
        ("TEXTCOLOR",     (0, 0), (-1, 0),  colors.white),
        ("FONTNAME",      (0, 0), (-1, 0),  "Helvetica-Bold"),
        ("FONTSIZE",      (0, 0), (-1, 0),  8),
        ("TOPPADDING",    (0, 0), (-1, -1), 4),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
        ("LEFTPADDING",   (0, 0), (-1, -1), 6),
        ("RIGHTPADDING",  (0, 0), (-1, -1), 6),
        ("GRID",          (0, 0), (-1, -1), 0.4, _BORDER),
        ("VALIGN",        (0, 0), (-1, -1), "MIDDLE"),
    ]
    for i in range(1, len(task_data)):
        if i % 2 == 0:
            task_style.append(("BACKGROUND", (0, i), (-1, i), _ROW_ALT))
    task_table.setStyle(TableStyle(task_style))
    story.append(task_table)
    story.append(Spacer(1, 10))

    # ── Evaluation Result ──────────────────────────────────────────────
    story.append(_section_header("EVALUATION RESULT"))
    story.append(Spacer(1, 6))

    result       = evaluation_row.get("result", "—")
    result_style = result_style_pass if result == "PASS" else result_style_fail
    story.append(Paragraph(result, result_style))

    comments = evaluation_row.get("comments")
    if comments:
        story.append(Spacer(1, 6))
        story.append(Paragraph("COMMENTS", field_label_style))
        story.append(Spacer(1, 3))
        story.append(Paragraph(comments, objective_style))
    story.append(Spacer(1, 10))

    # ── Signatures ─────────────────────────────────────────────────────
    story.append(_section_header("SIGNATURES"))
    story.append(Spacer(1, 6))

    sig_date      = evaluation_row.get("signature_date", "—")
    remedial_date = evaluation_row.get("remedial_date") or "N/A"

    sig_data = [
        [
            Paragraph("OBSERVER",           field_label_style),
            Paragraph("OBSERVER SIGNATURE", field_label_style),
            Paragraph("TRAINEE SIGNATURE",  field_label_style),
        ],
        [
            Paragraph(evaluation_row.get("observer_name",      "—"), field_value_style),
            Paragraph(evaluation_row.get("observer_signature", "—"), field_value_style),
            Paragraph(evaluation_row.get("trainee_signature",  "—"), field_value_style),
        ],
        [
            Paragraph("SIGNATURE DATE",    field_label_style),
            Paragraph("REMEDIAL JPM DATE", field_label_style),
            Paragraph("",                  field_label_style),
        ],
        [
            Paragraph(sig_date,      field_value_style),
            Paragraph(remedial_date, field_value_style),
            Paragraph("",            field_value_style),
        ],
    ]
    sig_table = Table(sig_data, colWidths=[usable_width / 3] * 3)
    sig_table.setStyle(TableStyle([
        ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
        ("TOPPADDING",    (0, 0), (-1, -1), 2),
        ("LINEBELOW",     (0, 0), (-1, 1),  0.5, colors.HexColor("#cccccc")),
    ]))
    story.append(sig_table)
    story.append(Spacer(1, 12))

    # ── Footer ─────────────────────────────────────────────────────────
    story.append(HRFlowable(width="100%", thickness=0.5, color=colors.grey))
    story.append(Spacer(1, 4))
    submitted_by = evaluation_row.get("submitted_by", "—")
    submitted_at = evaluation_row.get("submitted_at", "—")
    story.append(Paragraph(
        f"Generated by: {submitted_by}  |  {submitted_at}",
        footer_style,
    ))

    doc.build(story)
    return buffer.getvalue()