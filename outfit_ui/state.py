"""Shared login and selected-analysis state for a Streamlit session."""

import streamlit as st


def sign_out():
    for key in list(st.session_state):
        del st.session_state[key]


def select_record(record):
    st.session_state["active_id"] = record["id"]
    st.session_state["active_status"] = record["status"]


def clear_record():
    st.session_state.pop("active_id", None)
    st.session_state.pop("active_status", None)
