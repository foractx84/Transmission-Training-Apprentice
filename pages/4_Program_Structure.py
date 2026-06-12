"""Program Structure page — documentation, reporting, and communication flows."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

import streamlit as st
from app.components.navigation import require_auth, render_sidebar
from app.core.rbac import has_role, ROLE_ADMIN, ROLE_SUPERVISOR, ROLE_AUDITOR

def main() -> None:
    auth = require_auth()
    render_sidebar(auth)

    if not any(has_role(auth, r) for r in [ROLE_SUPERVISOR, ROLE_ADMIN, ROLE_AUDITOR]):
        st.error("🚫 Access Denied — This page is restricted to supervisors, admins, and auditors.")
        st.stop()

    st.title("Program Structure")
    st.markdown("---")
    st.info("🚧 Program Structure view coming soon.")


main()
