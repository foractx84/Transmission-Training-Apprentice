"""Shared navigation component — auth guard and consistent sidebar."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent.parent))

import streamlit as st
from app.core.auth import AzureAuth
from app.core.config import get_azure_config


def hide_sidebar() -> None:
    """Inject CSS to hide the sidebar and its navigation items."""
    st.markdown(
        """
        <style>
        [data-testid="stSidebar"] { display: none !important; }
        [data-testid="collapsedControl"] { display: none !important; }
        </style>
        """,
        unsafe_allow_html=True,
    )


def require_auth() -> AzureAuth:
    """
    Auth guard — must be called at the top of every page.
    Stops rendering and shows a login prompt if the user is not authenticated.
    Returns the AzureAuth instance on success.
    """
    azure_config = get_azure_config()
    if not azure_config:
        hide_sidebar()
        st.error("Azure configuration not found. Please check your .env file.")
        st.stop()

    auth = AzureAuth(azure_config)

    if not auth.is_authenticated():
        hide_sidebar()
        st.switch_page("main.py")

    return auth


def render_sidebar(auth: AzureAuth) -> dict:
    """
    Render the consistent sidebar: user info, access details, and logout.
    Returns the user_info dict.
    """
    st.markdown(
        """
        <style>
        .block-container { padding-top: 1rem !important; }
        h1 { margin-bottom: 0 !important; }
        </style>
        """,
        unsafe_allow_html=True,
    )

    user_info = auth.get_user_info() or {}

    with st.sidebar:
        st.title("⚡ Transmission Training")
        st.divider()

        display_name = user_info.get("displayName") or user_info.get("name", "User")
        email = user_info.get("mail") or user_info.get("userPrincipalName", "")

        st.write(f"**{display_name}**")
        if email:
            st.caption(email)

        user_roles = auth.get_user_roles()
        user_groups = auth.get_user_groups()

        if user_roles or user_groups:
            with st.expander("🔐 Access details", expanded=False):
                if user_roles:
                    st.markdown("**Roles**")
                    for r in user_roles:
                        st.caption(f"- {r}")
                if user_groups:
                    st.markdown("**Groups**")
                    for g in user_groups:
                        st.caption(f"- {g.get('name', g.get('id', ''))}")

        st.divider()

        if st.button("🚪 Logout", use_container_width=True):
            auth.logout()

    return user_info
