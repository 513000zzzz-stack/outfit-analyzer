"""Image upload and analysis submission."""

import streamlit as st

from ..client import ApiError, fetch_data
from ..state import select_record


def submit_panel():
    st.subheader("01  上传穿搭照片")
    left, right = st.columns([3, 2], gap="large")
    with left:
        with st.form("upload", clear_on_submit=True):
            image = st.file_uploader(
                "选择照片（JPG、PNG 或 WebP）",
                type=["jpg", "jpeg", "png", "webp"],
                help="图片不超过 10 MB。",
            )
            st.caption("提交后，照片会在本机或服务器运行 YOLO，并发送至豆包接口分析。")
            submitted = st.form_submit_button("提交双方案分析", type="primary")
    with right:
        st.markdown("**比较什么？**")
        st.write("YOLO 标出服饰位置，并从检测区域统计颜色。豆包解释画面中的穿搭、配色关系和搭配建议。")
    if not submitted:
        return
    if image is None:
        st.warning("请选择要分析的照片。")
        return
    try:
        with st.spinner("正在上传照片并创建任务…"):
            record = fetch_data(
                "POST", "/api/analysis/create",
                files={"image": (image.name, image.getvalue(), image.type)},
            )
    except ApiError as error:
        st.error(str(error))
        return
    select_record(record)
    st.rerun()
