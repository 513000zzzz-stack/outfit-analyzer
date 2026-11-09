"""Compose the account, history, upload, and result views."""

import streamlit as st

from .styles import STYLES
from .views.account import login_page, restore_cookie_login
from .views.analysis import submit_panel
from .views.history import history_sidebar
from .views.results import comparison_panel


def main():
    st.set_page_config(page_title="穿搭分析台", page_icon="◈", layout="wide")
    st.markdown(STYLES, unsafe_allow_html=True)
    st.markdown(
        '<section class="studio-intro"><small>OUTFIT ANALYZER </small>'
        '<h1>同一张照片，两种视角</h1>'
        '<p>并排比较服饰检测、颜色统计和多模态穿搭分析。</p></section>',
        unsafe_allow_html=True,
    )
    restore_cookie_login()
    if "access_token" not in st.session_state:
        login_page()
        return
    history_sidebar()
    submit_panel()
    comparison_panel()
