"""
Transmission Apprentice Training App — Home / Login
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

import streamlit as st
from app.core.auth import AzureAuth
from app.core.config import get_azure_config
from app.core.rbac import has_role, ROLE_ADMIN, ROLE_SUPERVISOR, ROLE_APPRENTICE, ROLE_AUDITOR
from app.components.navigation import hide_sidebar

st.set_page_config(
    page_title="Transmission Apprentice Training",
    page_icon="⚡",
    layout="wide",
)


def main():
    azure_config = get_azure_config()

    if not azure_config:
        st.error("Azure configuration not found. Please check your .env file.")
        return

    auth = AzureAuth(azure_config)

    if not auth.is_authenticated():
        hide_sidebar()

        st.markdown(
            """
            <style>
            .block-container { padding-top: 3rem !important; }
            h1 { margin-bottom: 0 !important; }
            </style>
            """,
            unsafe_allow_html=True,
        )

        st.title("⚡ Transmission Apprentice Training")
        st.markdown("---")
        st.markdown("### Welcome")
        st.write("Please log in with your Azure AD account to access the training portal.")
        auth.login()
        return

    # ── Build page list based on role ─────────────────────────────────────────
    pages = []

    if has_role(auth, ROLE_APPRENTICE):
        pages.append(st.Page("pages/1_Apprentice_Records.py",
                             title="Apprentice Records", icon="📋"))

    if any(has_role(auth, r) for r in [ROLE_SUPERVISOR, ROLE_ADMIN, ROLE_AUDITOR]):
        pages.append(st.Page("pages/2_Class_Standing.py",
                             title="Class Standing",    icon="🏆"))
        pages.append(st.Page("pages/3_Program_Analytics.py",
                             title="Program Analytics", icon="📊"))
        pages.append(st.Page("pages/4_Program_Structure.py",
                             title="Program Structure", icon="🏗️"))

    if has_role(auth, ROLE_SUPERVISOR) or has_role(auth, ROLE_ADMIN):
        pages.append(st.Page("pages/6_JPM_HOSD.py",
                             title="JPM & HOSD",        icon="📝"))

    # Security Admin page hidden from UI for now
    # if has_role(auth, ROLE_ADMIN):
    #     pages.append(st.Page("pages/5_Security_Admin.py",
    #                          title="Security Admin",    icon="🔐"))

    if not pages:
        st.error("⚠️ No roles assigned to your account.")
        st.write("Please contact your administrator to be assigned a role.")
        st.stop()

    pg = st.navigation(pages)
    pg.run()


if __name__ == "__main__":
    main()
