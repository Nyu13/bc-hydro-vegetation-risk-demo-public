"""Runtime Light/Dark theme via CSS (Streamlit has no official in-app theme API)."""

from __future__ import annotations

import streamlit as st

_LIGHT = """
<style>
  html, body, .stApp, [data-testid="stAppViewContainer"] {
    background-color: #ffffff !important;
    color: #212529 !important;
  }
  [data-testid="stHeader"] { background-color: #ffffff !important; border-bottom: 1px solid #e9ecef; }
  section[data-testid="stSidebar"] {
    background-color: #f8f9fa !important;
    border-right: 1px solid #e9ecef;
  }
  section[data-testid="stSidebar"] p, section[data-testid="stSidebar"] span, section[data-testid="stSidebar"] label {
    color: #212529 !important;
  }
  .block-container { color: #212529 !important; }
  div[data-testid="stMetricValue"] { color: #198754 !important; }
  div[data-testid="stMetricLabel"] { color: #495057 !important; }
  [data-testid="stExpander"] { background-color: #ffffff !important; border: 1px solid #dee2e6 !important; }
  [data-testid="stVerticalBlock"] > div { background-color: transparent !important; }
  .stTabs [data-baseweb="tab-list"] { background-color: #f8f9fa !important; }
  .stTabs [aria-selected="true"] { color: #198754 !important; }
</style>
"""

_DARK = """
<style>
  html, body, .stApp, [data-testid="stAppViewContainer"] {
    background-color: #0e1117 !important;
    color: #fafafa !important;
  }
  [data-testid="stHeader"] { background-color: #0e1117 !important; border-bottom: 1px solid #30363d; }
  section[data-testid="stSidebar"] {
    background-color: #262730 !important;
    border-right: 1px solid #30363d;
  }
  section[data-testid="stSidebar"] p, section[data-testid="stSidebar"] span, section[data-testid="stSidebar"] label {
    color: #fafafa !important;
  }
  .block-container { color: #fafafa !important; }
  div[data-testid="stMetricValue"] { color: #7fdbca !important; }
  div[data-testid="stMetricLabel"] { color: #a0a8b0 !important; }
  [data-testid="stExpander"] { background-color: #262730 !important; border: 1px solid #3d4454 !important; }
  [data-testid="stVerticalBlock"] > div { background-color: transparent !important; }
  .stTabs [data-baseweb="tab-list"] { background-color: #262730 !important; }
  .stTabs [aria-selected="true"] { color: #7fdbca !important; }
  div[data-testid="stMarkdownContainer"] p, div[data-testid="stMarkdownContainer"] li {
    color: #e6e6e6 !important;
  }
</style>
"""


def apply_streamlit_theme(theme: str) -> None:
    """Inject CSS for Light or Dark. Call once per run after sidebar theme selection."""
    css = _DARK if str(theme).strip().lower() == "dark" else _LIGHT
    st.markdown(css, unsafe_allow_html=True)
