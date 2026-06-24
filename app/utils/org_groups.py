"""Map cost-center descriptions (org_group) → business groups.

The view exposes `org_group` = COSTCENTER_DESCRIPTION, which is NOT literally
"Transmission" / "Distribution" / "Substation". The dropdown on Program
Analytics / Class Standing needs those three clean groups, so we classify each
cost center here.

HOW TO FINISH THE MAPPING:
  1. Open Program Analytics — the sidebar shows an "Org mapping" panel listing
     every cost center that is still UNMAPPED (plus how many apprentices).
  2. For each, add a keyword → group rule to _RULES below (matched
     case-insensitively, first match wins).
  3. Reload. The unmapped list shrinks until it's empty.

Keep rules ordered most-specific first (e.g. "SUBSTATION" before "SUB").
"""
from __future__ import annotations

# The business groups the dropdown offers (besides "All Electric").
BUSINESS_GROUPS = ["Transmission", "Distribution", "Substation", "Metering", "Generation"]

# Label used for any cost center that no rule matches yet.
UNMAPPED = "Unmapped"

# Ordered (keyword, group) rules. Keyword is matched as a case-insensitive
# substring of the cost-center description. EDIT THIS using the in-app panel.
_RULES: list[tuple[str, str]] = [
    # Most-specific / unambiguous first.
    ("SUBSTATION",       "Substation"),
    ("SUB STA",          "Substation"),
    ("TRANSMISSION",     "Transmission"),
    ("GENERATION",       "Generation"),
    ("CULLEY",           "Generation"),   
    ("METERING",         "Metering"),
    ("DISTRIBUT",        "Distribution"),
    ("UNDERGROUND",      "Distribution"),
    ("UG OPERATIONS",    "Distribution"),
    ("FIELD OPERATIONS", "Distribution"),    
]


def classify_business_group(cost_center: str | None) -> str:
    """Return 'Transmission' / 'Distribution' / 'Substation', or UNMAPPED."""
    if not cost_center:
        return UNMAPPED
    text = cost_center.upper()
    for keyword, group in _RULES:
        if keyword.upper() in text:
            return group
    return UNMAPPED
