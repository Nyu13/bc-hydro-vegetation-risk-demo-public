"""Runtime Light/Dark theme via scoped CSS (avoids breaking tabs, widgets, and alerts)."""

from __future__ import annotations

import streamlit as st

# Scoped to the main app shell — avoid html/body and broad .block-container color rules
# that hide tab labels, break st.selectbox, or wash out st.warning/st.info text.

_LIGHT = """
<style>
  [data-testid="stAppViewContainer"] {
    background-color: #ffffff !important;
    color: #212529 !important;
  }
  [data-testid="stHeader"] {
    background-color: #ffffff !important;
    border-bottom: 1px solid #e9ecef;
  }
  section[data-testid="stSidebar"] {
    background-color: #f8f9fa !important;
    border-right: 1px solid #e9ecef;
  }
  section[data-testid="stSidebar"] label,
  section[data-testid="stSidebar"] p,
  section[data-testid="stSidebar"] span {
    color: #212529 !important;
  }
  /* Inputs/selects */
  [data-baseweb="select"] > div,
  [data-baseweb="select"] input,
  [data-baseweb="input"] > div,
  [data-baseweb="input"] input {
    background: #ffffff !important;
    color: #212529 !important;
    border-color: #ced4da !important;
  }
  [role="listbox"] {
    background: #ffffff !important;
    border: 1px solid #ced4da !important;
  }
  [role="option"] {
    color: #212529 !important;
    background: #ffffff !important;
  }
  [role="option"][aria-selected="true"] {
    background: #e9f5ee !important;
    color: #198754 !important;
  }
  /* Tabs: make unselected labels visible on light background */
  [data-testid="stTabs"] button[data-baseweb="tab"] {
    color: #212529 !important;
  }
  [data-testid="stTabs"] button[data-baseweb="tab"][aria-selected="true"] {
    color: #198754 !important;
    border-bottom: 2px solid #198754 !important;
  }
  [data-testid="stTabs"] [role="tab"] {
    color: #212529 !important;
  }
  [data-testid="stTabs"] [role="tab"][aria-selected="true"] {
    color: #198754 !important;
  }
  div[data-testid="stMetricValue"] {
    color: #198754 !important;
    font-size: 1.35rem !important;
    line-height: 1.2 !important;
    overflow-wrap: anywhere;
  }
  div[data-testid="stMetricLabel"] {
    color: #495057 !important;
    font-size: 0.8rem !important;
    line-height: 1.25 !important;
  }
  /* Dataframes/tables */
  [data-testid="stDataFrame"] {
    background: #ffffff !important;
    border: 1px solid #dee2e6 !important;
  }
  [data-testid="stDataFrame"] * {
    color: #212529 !important;
  }
  [data-testid="stDataFrame"] [role="columnheader"] {
    background: #f8f9fa !important;
    color: #212529 !important;
  }
</style>
"""

_DARK = """
<style>
  [data-testid="stAppViewContainer"] {
    background-color: #0e1117 !important;
    color: #fafafa !important;
  }
  [data-testid="stHeader"] {
    background-color: #0e1117 !important;
    border-bottom: 1px solid #30363d;
  }
  section[data-testid="stSidebar"] {
    background-color: #262730 !important;
    border-right: 1px solid #30363d;
  }
  section[data-testid="stSidebar"] label,
  section[data-testid="stSidebar"] p,
  section[data-testid="stSidebar"] span {
    color: #fafafa !important;
  }
  /* Inputs/selects */
  [data-baseweb="select"] > div,
  [data-baseweb="select"] input,
  [data-baseweb="input"] > div,
  [data-baseweb="input"] input {
    background: #1f2430 !important;
    color: #fafafa !important;
    border-color: #3d4454 !important;
  }
  [role="listbox"] {
    background: #1f2430 !important;
    border: 1px solid #3d4454 !important;
  }
  [role="option"] {
    color: #fafafa !important;
    background: #1f2430 !important;
  }
  [role="option"][aria-selected="true"] {
    background: #26333a !important;
    color: #7fdbca !important;
  }
  [data-testid="stTabs"] button[data-baseweb="tab"] {
    color: #d0d7de !important;
  }
  [data-testid="stTabs"] button[data-baseweb="tab"][aria-selected="true"] {
    color: #7fdbca !important;
    border-bottom: 2px solid #7fdbca !important;
  }
  [data-testid="stTabs"] [role="tab"] {
    color: #d0d7de !important;
  }
  [data-testid="stTabs"] [role="tab"][aria-selected="true"] {
    color: #7fdbca !important;
  }
  div[data-testid="stMetricValue"] {
    color: #7fdbca !important;
    font-size: 1.35rem !important;
    line-height: 1.2 !important;
    overflow-wrap: anywhere;
  }
  div[data-testid="stMetricLabel"] {
    color: #a0a8b0 !important;
    font-size: 0.8rem !important;
    line-height: 1.25 !important;
  }
  /* Dataframes/tables */
  [data-testid="stDataFrame"] {
    background: #1f2430 !important;
    border: 1px solid #3d4454 !important;
  }
  [data-testid="stDataFrame"] * {
    color: #fafafa !important;
  }
  [data-testid="stDataFrame"] [role="columnheader"] {
    background: #2a3140 !important;
    color: #d0d7de !important;
  }
</style>
"""


def apply_streamlit_theme(theme: str) -> None:
    """Inject scoped CSS once per run."""
    css = _DARK if str(theme).strip().lower() == "dark" else _LIGHT
    st.markdown(css, unsafe_allow_html=True)
