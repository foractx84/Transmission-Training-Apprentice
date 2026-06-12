"""Security & Admin page — program settings, access control, and change flow."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

import streamlit as st
from app.components.navigation import require_auth, render_sidebar
from app.core.rbac import has_role, ROLE_ADMIN

def main() -> None:
    auth = require_auth()
    render_sidebar(auth)

    if not has_role(auth, ROLE_ADMIN):
        st.error("🚫 Access Denied — This page is restricted to administrators only.")
        st.stop()

    st.title("Security & Admin")
    st.markdown("---")
    st.info("🚧 Security & Admin view coming soon.")


main()
