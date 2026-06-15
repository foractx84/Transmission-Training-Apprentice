# Data-Layer Change Spec — `vw_apprentice_records`

**For:** Churon / Rebecca (data / BigQuery view owners)
**From:** App team (Transmission Apprentice Training App)
**Date:** 2026-06-15
**Purpose:** The Streamlit app reads almost everything from the BigQuery view
`{project}.{dataset}.vw_apprentice_records`. Several items from the technical
review (incorrect 121% completion, unfiltered population, org-group filtering,
"last 5 years" trend, year columns) **cannot be fixed in app code alone** — they
require new columns and/or definitions in this view. This document specifies
exactly what the app needs and why.

---

## 1. Background — how the app uses the view today

- The app's only population filter today is `WHERE apprentice_name IS NOT NULL`.
  No filtering by discipline, employment status, program membership, or course type.
- Completion % is computed in the app's SQL as
  `SUM(is_completed) / COUNT(DISTINCT course_id) * 100`. Because the numerator
  sums **rows** and the denominator counts **distinct courses**, a course with
  multiple rows (retake / multiple sections / re-qual) pushes the result above
  100% — this is the reported **121%**. The app will also switch to
  `COUNT(DISTINCT IF(is_completed, course_id, NULL))` on its side, but the view
  must still expose a clean way to count **only program courses**.

---

## 2. Columns the app needs added to the view

| # | Column | Type | Definition needed from you | Drives review item |
|---|--------|------|----------------------------|--------------------|
| 1 | `program_family` | STRING | Value identifying Electric apprentices (e.g. `'Electric'`). Used to exclude all non-Electric / unrelated training users. | 1.1 |
| 2 | `org_group` (or `discipline`) | STRING | One of `Transmission` / `Distribution` / `Substation` for each apprentice. This is the dropdown the business asked for ("All Electric" default). | 1.1, 2.3, 3.1 |
| 3 | `is_active_employee` | BOOL | TRUE only if the employee is currently active (not terminated / separated). Please define the exact source/rule (e.g. SAP employment status, termination_date IS NULL). | 1.2, 3.3 |
| 4 | `is_in_apprentice_program` | BOOL | TRUE only if the employee is currently enrolled in the apprenticeship program (not a past participant, not company-wide-training-only). Please define the rule. | 1.2, 3.3 |
| 5 | `is_program_course` | BOOL | TRUE only if the course/task belongs to the apprenticeship program. FALSE for company-wide training, safety training, general compliance, and unrelated Docebo courses. This is the key fix for the >100% completion math. | 1.3, 2.1, 4.4 |
| 6 | `apprentice_year` | INT64 or STRING | **OPEN QUESTION (see §4).** 1st–4th program year. Needed for the new year-column chart. | 3.4 |

> Columns 3, 4, and 5 are the highest priority — they fix the incorrect
> percentages and the inflated population, which appear across review sections
> 1, 2.1, 3.3, and 4.4.

---

## 3. How the app will use each column (so definitions match intent)

Once the columns exist, the app will apply a shared base filter on every loader
(`load_apprentices`, `load_class_standing`, `load_program_analytics`,
`load_analytics_trend`):

```sql
WHERE apprentice_name IS NOT NULL
  AND program_family = 'Electric'
  AND is_active_employee = TRUE
  AND is_in_apprentice_program = TRUE
```

For completion math, the app additionally restricts to program courses and makes
the numerator/denominator consistent:

```sql
LEAST(
  ROUND(
    SAFE_DIVIDE(
      COUNT(DISTINCT IF(is_completed AND is_program_course, course_id, NULL)),
      COUNT(DISTINCT IF(is_program_course, course_id, NULL))
    ) * 100, 1),
  100.0
) AS completion_pct
```

The org-group dropdown will filter `WHERE org_group = @selected` (default
"All Electric" = no org filter, Electric base filter still applies).

The 5-year trend will add `AND completion_date >= DATE_SUB(CURRENT_DATE(), INTERVAL 5 YEAR)`.

---

## 4. OPEN QUESTION — apprentice year (item 3.4)

The review asks for columns by **1st / 2nd / 3rd / 4th Year Appr.** The app
currently only has `apprenticeship_level` (`Level 1`–`Level 4`, `Journeyman`).

**Please confirm one of:**

- **(a)** Program year maps directly from `apprenticeship_level`
  (Level 1 = 1st Year, …). → No view change needed; the app derives year from level.
- **(b)** Program year is tracked independently of level. → Please add an
  `apprentice_year` column (definition + source).

We will not build the year-column chart until this is confirmed.

---

## 5. Definitions still needed from the business (not blocking the columns)

These don't block the view work but are flagged so nothing is assumed:

- Exact rule for **"active"** (column 3) and **"in program"** (column 4).
- Exact rule for what makes a course **program vs non-program** (column 5) —
  e.g. a course-catalog flag, a naming convention, or an explicit allow-list.

---

## 6. Requested deliverable

An updated `vw_apprentice_records` (or a sibling view) exposing columns 1–5
(and 6 if answer is **(b)**), with the definitions above documented. The app
team will then update the SQL in `app/services/analytics_service.py` to use them.
