"""Session state helpers for managing application state across pages."""
import streamlit as st
from typing import Any


def get_session(key: str, default: Any = None) -> Any:
    return st.session_state.get(key, default)


def set_session(key: str, value: Any) -> None:
    st.session_state[key] = value


def clear_session(key: str) -> None:
    if key in st.session_state:
        del st.session_state[key]


def init_session(key: str, default: Any) -> Any:
    """Initialize a session key if not already set. Returns the value."""
    if key not in st.session_state:
        st.session_state[key] = default
    return st.session_state[key]
