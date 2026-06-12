"""Mock data for development and testing before BigQuery integration."""
from datetime import date, timedelta

TODAY = date.today()

MOCK_APPRENTICES = [
    {
        "id": "A001",
        "name": "John Smith",
        "level": "Level 2",
        "enrolled_courses": 3,
        "open_tasks": 5,
        "delayed_tasks": 1,
        "program_alerts": 2,
        "start_date": date(2023, 5, 1),
        "expected_completion": date(2026, 6, 1),
    },
    {
        "id": "A002",
        "name": "Maria Garcia",
        "level": "Level 3",
        "enrolled_courses": 4,
        "open_tasks": 2,
        "delayed_tasks": 0,
        "program_alerts": 1,
        "start_date": date(2022, 9, 15),
        "expected_completion": date(2025, 9, 15),
    },
]

MOCK_MILESTONES = [
    {"level": "Level 1", "name": "Basic Safety",        "status": "Completed"},
    {"level": "Level 1", "name": "Tools & Equipment",   "status": "Completed"},
    {"level": "Level 2", "name": "Line Construction",   "status": "In Progress"},
    {"level": "Level 2", "name": "Substation Basics",   "status": "Open"},
    {"level": "Level 3", "name": "Advanced Line Work",  "status": "Open"},
]

MOCK_TRAINING_SUMMARY = [
    {
        "date": TODAY - timedelta(days=12),
        "topic": "Overhead Line Safety",
        "instructor": "R. Johnson",
        "hours": 8.0,
        "status": "Completed",
        "notes": "Covered PPE requirements and fall protection.",
    },
    {
        "date": TODAY - timedelta(days=5),
        "topic": "Transformer Installation",
        "instructor": "K. Williams",
        "hours": 16.0,
        "status": "Completed",
        "notes": "Hands-on installation and testing procedures.",
    },
    {
        "date": TODAY + timedelta(days=7),
        "topic": "Underground Cable Systems",
        "instructor": "T. Brown",
        "hours": 8.0,
        "status": "Scheduled",
        "notes": "Cable splicing and fault location.",
    },
]

MOCK_DOCS_ALERTS = [
    {
        "type": "Alert",
        "message": "Safety certification renewal due in 30 days",
        "priority": "High",
    },
    {
        "type": "Document",
        "message": "Q1 Progress Report submitted",
        "priority": "Info",
    },
    {
        "type": "Alert",
        "message": "Level 2 milestone review required",
        "priority": "Medium",
    },
    {
        "type": "Document",
        "message": "OSHA training log updated",
        "priority": "Info",
    },
]
