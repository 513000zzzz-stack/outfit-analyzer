"""HTTP access to the authenticated FastAPI service.

所有 JSON 接口统一返回 ``{"code": ..., "message": ..., "data": ...}``，
页面只关心其中的 ``data``，因此这里提供 :func:`fetch_data` 统一解包。
"""

import os
from urllib.parse import quote

import httpx
import streamlit as st

from .state import sign_out


API_URL = os.getenv("API_URL", "http://127.0.0.1:8000").rstrip("/")


class ApiError(RuntimeError):
    def __init__(self, message, status_code=None):
        super().__init__(message)
        self.status_code = status_code


def request_api(method, path, *, protected=True, token=None, **kwargs):
    headers = {}
    if protected:
        token = st.session_state["access_token"]
    if token:
        headers["Authorization"] = f"Bearer {token}"
    try:
        response = httpx.request(method, API_URL + path, headers=headers, timeout=20, **kwargs)
    except httpx.RequestError as error:
        raise ApiError("无法连接分析服务。请确认 FastAPI 已启动，再重试。") from error

    if response.is_error:
        try:
            payload = response.json()
            detail = payload.get("message", payload.get("detail"))
        except (ValueError, AttributeError):
            detail = None
        if protected and response.status_code == 401:
            sign_out()
            st.session_state["flash"] = "登录已过期，请重新登录。"
            st.rerun()
        if isinstance(detail, str):
            message = detail
        elif response.status_code == 422:
            message = "输入不符合要求。请检查用户名、密码或上传文件。"
        else:
            message = f"服务请求失败（HTTP {response.status_code}）。"
        raise ApiError(message, response.status_code)
    return response


def fetch_data(method, path, **kwargs):
    """调用接口并返回统一结构中的 data。"""
    return request_api(method, path, **kwargs).json()["data"]


def record_path(record_id):
    return f"/api/analysis/detail/{quote(str(record_id), safe='')}"


def file_path(record_id, name):
    return f"/api/analysis/file/{quote(str(record_id), safe='')}/{quote(str(name), safe='')}"
