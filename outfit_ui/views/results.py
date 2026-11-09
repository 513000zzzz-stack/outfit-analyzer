"""Task status, side-by-side results, notes, and record deletion."""

import re

import streamlit as st

from ..client import ApiError, fetch_data, file_path, record_path, request_api
from ..state import clear_record
from ..styles import display_time


ACTIVE = {"queued", "running"}
STATUS = {
    "queued": "排队中",
    "running": "分析中",
    "completed": "分析完成",
    "partial": "部分完成",
    "failed": "分析失败",
}


def show_image(record_id, filename, caption, *, optional=False, width=None):
    try:
        image = request_api("GET", file_path(record_id, filename)).content
    except ApiError as error:
        if not (optional and error.status_code == 404):
            st.caption(f"{caption}暂不可用。{error}")
        return
    if width:
        st.image(image, caption=caption, width=width)
    else:
        st.image(image, caption=caption, use_container_width=True)


def pending_or_error(result, pending):
    if not result:
        st.caption("等待此方案完成。" if pending else "这一路没有可展示的结果。")
        return True
    if result["status"] != "ok":
        st.error(result.get("error") or "这一路分析未成功。")
        return True
    return False


def elapsed_label(seconds):
    return f"{seconds:.2f} 秒" if isinstance(seconds, (float, int)) else "—"


def show_yolo(record_id, result, pending):
    st.markdown("#### YOLO · 检测与颜色统计")
    if pending_or_error(result, pending):
        return
    data = result.get("data") or {}
    objects = data.get("objects") or []
    metric_a, metric_b = st.columns(2)
    metric_a.metric("检测目标", len(objects))
    metric_b.metric("耗时", elapsed_label(result.get("seconds")))
    show_image(record_id, "detection.jpg", "服饰检测结果", optional=True)

    colors = data.get("color_analysis") or {}
    if description := colors.get("description"):
        st.write(description)
    if colors.get("palette"):
        swatches = []
        for item in colors["palette"][:5]:
            color, ratio = item.get("hex", ""), item.get("ratio")
            if re.fullmatch(r"#[0-9A-Fa-f]{6}", color) and isinstance(ratio, (int, float)):
                swatches.append(
                    f'<span class="color-swatch"><span class="color-chip" '
                    f'style="background:{color}"></span><small>{ratio:.1%}</small></span>'
                )
        if swatches:
            st.markdown("**主要颜色占比**")
            st.markdown("".join(swatches), unsafe_allow_html=True)
        else:
            show_image(record_id, "overall_palette.png", "整体色卡", optional=True)
    limitations = data.get("limitations")
    with st.expander("完整 YOLO 文字分析", expanded=True):
        try:
            report = request_api("GET", file_path(record_id, "analysis.txt")).text
        except ApiError as error:
            if error.status_code == 404:
                st.caption("这条记录没有保存完整的文字报告。")
            else:
                st.caption(f"文字报告暂不可用。{error}")
        else:
            if limitations:
                report = report.partition("\n四、分析依据与局限")[0].rstrip()
            st.text(report)
    if objects:
        with st.expander("查看检测明细"):
            rows = [
                {
                    "类别": item.get("class_name", "未知"),
                    "置信度": f"{item['confidence']:.1%}" if "confidence" in item else "—",
                    "主要颜色": ", ".join(c.get("name", "") for c in item.get("colors", [])[:3]),
                }
                for item in objects
            ]
            st.dataframe(rows, hide_index=True, use_container_width=True)
    if limitations:
        with st.expander("查看统计范围和局限"):
            for text in limitations:
                st.write(text)


def show_doubao(result, pending):
    st.markdown("#### 豆包 · 穿搭解读与建议")
    if pending_or_error(result, pending):
        return
    data = result.get("data") or {}
    usage = data.get("usage") or {}
    metric_a, metric_b = st.columns(2)
    metric_a.metric("耗时", elapsed_label(data.get("request_seconds", result.get("seconds"))))
    metric_b.metric("Token 用量", usage.get("total_tokens", "—"))
    if model := data.get("returned_model") or data.get("requested_model"):
        st.caption(f"模型 · {model}")
    st.text(data.get("answer") or "接口没有返回正文。")
    if data.get("finish_reason") == "length":
        st.info("回答达到长度上限，后半部分可能不完整。")


def manage_record(record):
    record_id = record["id"]
    with st.expander("编辑备注或删除记录"):
        with st.form(f"note_{record_id}"):
            note = st.text_area("我的对比观察", value=record.get("note") or "", max_chars=1000)
            save = st.form_submit_button("保存备注")
        if save:
            try:
                fetch_data("PUT", f"/api/analysis/note/{record_id}", json={"note": note})
                st.success("备注已保存。")
            except ApiError as error:
                st.error(str(error))
        confirm = st.checkbox("确认删除这条记录", key=f"confirm_{record_id}")
        if st.button("删除记录", disabled=not confirm, key=f"delete_{record_id}"):
            try:
                request_api("DELETE", f"/api/analysis/delete/{record_id}")
            except ApiError as error:
                st.error(str(error))
                return
            clear_record()
            st.rerun()


def comparison_panel():
    active_id = st.session_state.get("active_id")
    if not active_id:
        return
    st.divider()
    st.subheader("02  双方案对比")
    active = st.session_state.get("active_status") in ACTIVE

    @st.fragment(run_every=2 if active else None)
    def render_record():
        if st.button("刷新结果", key="refresh_active"):
            st.rerun(scope="app")
        try:
            record = fetch_data("GET", record_path(active_id))
        except ApiError as error:
            st.error(str(error))
            return
        status = record["status"]
        if status != st.session_state.get("active_status"):
            st.session_state["active_status"] = status
            if active and status not in ACTIVE:
                # 任务结束后回到整页重绘，停止自动刷新，避免持续轮询接口。
                st.rerun(scope="app")
        st.caption(f"{record['filename']} · {display_time(record.get('created_at'))}")
        pending = status in ACTIVE
        if pending:
            st.info(f"{STATUS[status]} · 页面会自动刷新进度。")
        elif status == "completed":
            st.success(STATUS[status])
        elif status == "partial":
            st.warning("部分完成 · 下面保留已成功的分析结果。")
        else:
            st.error("分析失败 · 请查看两路提示，或刷新记录。")
            if error := record.get("error"):
                st.caption(str(error))

        with st.expander("查看上传原图"):
            show_image(active_id, "input.jpg", "两套方案使用的原图", width=360)
        col_yolo, col_doubao = st.columns(2, gap="medium")
        with col_yolo, st.container(border=True):
            show_yolo(active_id, record.get("yolo"), pending)
        with col_doubao, st.container(border=True):
            show_doubao(record.get("doubao"), pending)
        if not pending:
            manage_record(record)

    render_record()
