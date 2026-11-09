"""Account entry, cookie recovery, and sign-out controls."""

import streamlit as st

from ..client import ApiError, fetch_data
from ..state import sign_out


_ACCOUNT_FORM = """
<form id="outfit-account-form" class="outfit-account-form" action="__ACTION__" method="post">
  <label for="outfit-username">用户名</label>
  <input id="outfit-username" name="username" autocomplete="username" required
         minlength="3" maxlength="32" pattern="[A-Za-z0-9_]+">
  <small>用户名须为 3–32 位英文字母、数字或下划线。</small>
  <label for="outfit-password">密码</label>
  <div class="outfit-password-field">
    <input id="outfit-password" name="password" type="password" autocomplete="__AUTOCOMPLETE__"
           required minlength="8" maxlength="128">
    <button type="button" class="outfit-password-toggle" aria-label="显示密码" aria-pressed="false">
      <svg data-eye="closed" viewBox="0 0 24 24" width="20" height="20" fill="none"
           stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">
        <path d="M3 10c2 3 5 5 9 5s7-2 9-5M6 13l-2 3m8-1v4m6-6 2 3"/>
      </svg>
      <svg data-eye="open" viewBox="0 0 24 24" width="20" height="20" fill="none"
           stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true" hidden>
        <path d="M2 12s4-6 10-6 10 6 10 6-4 6-10 6-10-6-10-6Z"/>
        <circle cx="12" cy="12" r="3"/>
      </svg>
    </button>
  </div>
  <small>密码至少 8 个字符，最多 128 个字符。</small>
  <p class="outfit-account-error" role="alert" hidden></p>
  <button type="submit" class="outfit-account-submit">__LABEL__</button>
</form>
<script>
(() => {
  const form = document.getElementById("outfit-account-form");
  if (!form || form.dataset.bound) return;
  form.dataset.bound = "true";
  const password = form.elements.password;
  const toggle = form.querySelector(".outfit-password-toggle");
  toggle.addEventListener("click", () => {
    const visible = password.type === "password";
    password.type = visible ? "text" : "password";
    toggle.setAttribute("aria-label", visible ? "隐藏密码" : "显示密码");
    toggle.setAttribute("aria-pressed", String(visible));
    toggle.querySelector('[data-eye="closed"]').toggleAttribute("hidden", visible);
    toggle.querySelector('[data-eye="open"]').toggleAttribute("hidden", !visible);
  });
  const alert = form.querySelector('[role="alert"]');
  const submit = form.querySelector('button[type="submit"]');
  form.addEventListener("submit", async (event) => {
    event.preventDefault();
    alert.hidden = true;
    submit.disabled = true;
    try {
      const fd = new FormData(form);
      const response = await fetch(form.action, {
        method: "POST",
        headers: {
          "Content-Type": "application/x-www-form-urlencoded"
        },
        body: new URLSearchParams(Object.fromEntries(fd)),
        credentials: "same-origin",
      });
      if (response.ok && response.redirected) {
        window.location.replace("/");
        return;
      }
      const body = await response.json().catch(() => null);
      if (typeof body?.detail === "string") {
        alert.textContent = body.detail;
      } else if (response.status === 422) {
        alert.textContent = "用户名或密码格式不符合要求：用户名 3–32 位字母、数字或下划线，密码 8–128 位。";
      } else {
        alert.textContent = `登录服务没有正常响应（HTTP ${response.status}）。请确认 FastAPI 已启动，并通过 nginx 入口访问本页。`;
      }
    } catch {
      alert.textContent = "无法连接服务，请稍后重试。";
    } finally {
      submit.disabled = false;
      alert.hidden = false;
    }
  });
})();
</script>
"""


def restore_cookie_login():
    if "access_token" in st.session_state:
        return
    token = st.context.cookies.get("outfit_token")
    if not token:
        return
    try:
        profile = fetch_data("GET", "/api/user/info", protected=False, token=token)
    except ApiError as error:
        if error.status_code != 401:
            st.error(str(error))
        return
    username = profile.get("username")
    if not username:
        return
    st.session_state["access_token"] = token
    st.session_state["username"] = username
    st.session_state["login_via_cookie"] = True
    st.html(
        '<script>fetch("/browser-auth/renew", {method: "POST", credentials: "same-origin"}).catch(() => {});</script>',
        unsafe_allow_javascript=True,
    )


def login_page():
    _, panel, _ = st.columns([1, 2, 1])
    with panel:
        if message := st.session_state.pop("flash", None):
            st.info(message)
        mode = st.radio("账户操作", ["登录", "注册"], horizontal=True)
        registering = mode == "注册"
        form = _ACCOUNT_FORM.replace(
            "__ACTION__", "/browser-auth/register" if registering else "/browser-auth/login"
        ).replace(
            "__AUTOCOMPLETE__", "new-password" if registering else "current-password"
        ).replace("__LABEL__", mode)
        st.html(form, unsafe_allow_javascript=True)


def account_controls():
    st.markdown("## 穿搭分析台")
    st.caption(f"当前账号 · {st.session_state['username']}")
    if st.session_state.get("login_via_cookie"):
        st.html('<p><a href="/browser-auth/logout" target="_self">退出登录</a></p>')
    elif st.button("退出登录", use_container_width=True):
        sign_out()
        st.rerun()
