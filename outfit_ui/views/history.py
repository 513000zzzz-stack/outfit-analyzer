"""History list and pagination controls."""

import streamlit as st

from ..client import ApiError, fetch_data
from ..state import select_record
from ..styles import display_time
from .account import account_controls


HISTORY_PAGE_SIZE = 20


def history_sidebar():
    with st.sidebar:
        account_controls()

        st.divider()
        st.markdown("### 我的分析")
        if st.button("刷新历史", use_container_width=True):
            st.session_state["history_page"] = 1
            st.rerun()
        page = st.session_state.get("history_page", 1)
        try:
            result = fetch_data(
                "GET", "/api/analysis/list", params={"page": page, "pageSize": HISTORY_PAGE_SIZE}
            )
        except ApiError as error:
            st.error(str(error))
            return
        records = result["list"]
        st.caption(f"共 {result['total']} 条 · 第 {page} 页")
        if page > 1 or result["hasMore"]:
            previous, following = st.columns(2)
            if previous.button("上一页", disabled=page == 1):
                st.session_state["history_page"] = page - 1
                st.rerun()
            if following.button("下一页", disabled=not result["hasMore"]):
                st.session_state["history_page"] = page + 1
                st.rerun()
        if not records:
            st.caption("这一页没有分析记录。" if page > 1 else "上传第一张图片后，分析记录会出现在这里。")
            return
        selected = st.selectbox(
            "选择历史记录",
            records,
            index=None,
            placeholder="按文件名查找",
            format_func=lambda row: (
                f"{row['filename']} · {display_time(row.get('created_at'))}"
            ),
        )
        if st.button("打开所选记录", disabled=selected is None, use_container_width=True):
            select_record(selected)
            st.rerun()
