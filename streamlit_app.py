from __future__ import annotations

from typing import Any, Dict, List, Optional

import requests
import streamlit as st
from app.core.config import settings

DEFAULT_API_BASE = "http://api:"+ str(settings.port)


def init_state() -> None:
    defaults: Dict[str, Any] = {
        "api_base": DEFAULT_API_BASE,
        "users_cache": [],
        "sessions_cache": [],
        "session_history": [],
        "active_user_id": None,
        "active_session_id": None,
        "direct_chat": [],
        "sessions_user": None,
    }
    for key, value in defaults.items():
        st.session_state.setdefault(key, value)


def api_base_url() -> str:
    base = DEFAULT_API_BASE
    if base and base != st.session_state.get("api_base"):
        st.session_state["api_base"] = base
    return base


def call_api(method: str, path: str, **kwargs) -> Optional[Any]:
    base = api_base_url()
    if not base:
        st.warning("Set the API base URL first.")
        return None

    url = f"{base}{path}"
    response: Optional[requests.Response] = None
    try:
        response = requests.request(method, url, timeout=15, **kwargs)
        response.raise_for_status()
    except requests.HTTPError as exc:
        detail = ""
        if response is not None:
            try:
                detail_json = response.json()
                detail = detail_json if isinstance(detail_json, str) else str(detail_json)
            except ValueError:
                detail = response.text
        st.error(f"{method} {path} failed: {exc}; {detail}")
        return None
    except requests.RequestException as exc:
        st.error(f"{method} {path} failed: {exc}")
        return None

    if response is None:
        return None

    content_type = response.headers.get("Content-Type", "")
    if "application/json" in content_type:
        try:
            return response.json()
        except ValueError:
            st.error("Invalid JSON response.")
            return None
    return response.text


def refresh_users() -> List[Dict[str, Any]]:
    data = call_api("GET", "/users/")
    if isinstance(data, list):
        st.session_state["users_cache"] = data
    return st.session_state["users_cache"]


def refresh_sessions(user_id: int) -> List[Dict[str, Any]]:
    data = call_api("GET", f"/chat/sessions/{user_id}")
    sessions = data.get("sessions", []) if isinstance(data, dict) else []
    st.session_state["sessions_cache"] = sessions
    st.session_state["sessions_user"] = user_id
    return sessions


def refresh_history(session_id: str) -> List[Dict[str, Any]]:
    data = call_api("GET", f"/chat/sessions/{session_id}/messages")
    records = data.get("messages", []) if isinstance(data, dict) else []
    st.session_state["session_history"] = records
    return records


def render_users_tab():
    st.subheader("Users")
    with st.form("create_user_form"):
        external_id = st.text_input("External ID", "")
        submitted = st.form_submit_button("Create user")
        if submitted:
            payload = {"external_id": external_id.strip()}
            if not payload["external_id"]:
                st.warning("External ID cannot be empty.")
            else:
                result = call_api("POST", "/users/", json=payload)
                if result:
                    st.success(f"User created with id={result['id']}.")
                    refresh_users()

    if st.button("Refresh users"):
        refresh_users()

    users = st.session_state.get("users_cache", [])
    if not users:
        st.info("No users found. Create one to get started.")
        return

    users_table = [
        {
            "id": user["id"],
            "external_id": user["external_id"],
            "created_at": user["created_at"],
            "updated_at": user["updated_at"],
        }
        for user in users
    ]
    st.dataframe(users_table, width='content', hide_index=True)


def render_sessions_tab():
    st.subheader("Chat Sessions")
    users = st.session_state.get("users_cache", [])
    user_options = {f"{u['external_id']} (#{u['id']})": u["id"] for u in users}

    selected_user_label = None
    if user_options:
        selected_user_label = st.selectbox("Select user", list(user_options.keys()))
        st.session_state["active_user_id"] = user_options[selected_user_label]
    else:
        st.info("Create a user first.")

    active_user_id = st.session_state.get("active_user_id")
    if active_user_id and active_user_id != st.session_state.get("sessions_user"):
        refresh_sessions(active_user_id)

    with st.form("create_session_form"):
        title = st.text_input("Session title", "")
        create_clicked = st.form_submit_button("Create session", disabled=not user_options)
        if create_clicked and st.session_state.get("active_user_id"):
            payload = {"user_id": st.session_state["active_user_id"], "title": title.strip() or None}
            result = call_api("POST", "/chat/sessions", json=payload)
            if result:
                st.success(f"Session created with id={result['id']}.")
                refresh_sessions(st.session_state["active_user_id"])

    cols = st.columns(2)
    with cols[0]:
        if st.button("Refresh sessions", disabled=not user_options):
            if st.session_state.get("active_user_id"):
                refresh_sessions(st.session_state["active_user_id"])

    sessions = st.session_state.get("sessions_cache", [])
    if not sessions:
        st.info("No sessions for the selected user yet.")
        return

    session_labels = [f"{item.get('title') or 'Untitled'} ({item['id']})" for item in sessions]
    label_to_id = {label: session["id"] for label, session in zip(session_labels, sessions)}

    selected_label = st.selectbox(
        "Active session",
        session_labels,
        index=session_labels.index(next((lbl for lbl, sid in label_to_id.items() if sid == st.session_state.get("active_session_id")), session_labels[0])) if session_labels else 0,
    )
    active_session = label_to_id.get(selected_label)

    if active_session and active_session != st.session_state.get("active_session_id"):
        st.session_state["active_session_id"] = active_session
        refresh_history(active_session)

    records = st.session_state.get("session_history", [])
    if records:
        st.markdown("### Session history")
        for record in records:
            role = record.get("role", "assistant")
            content = record.get("content", "")
            with st.chat_message(role):
                st.write(content)
    else:
        st.info("No messages in this session yet.")


def render_chat_tab():
    st.subheader("Session Chat")

    active_session = st.session_state.get("active_session_id")
    if not active_session:
        st.info("Select a session on the Sessions tab to enable session chat.")
        return

    history = st.session_state.get("session_history", [])
    for record in history:
        role = record.get("role", "assistant")
        content = record.get("content", "")
        with st.chat_message(role):
            st.write(content)

    with st.form("session_message_form"):
        message = st.text_area("Message", "", height=120)
        allow_tools = st.checkbox("Allow tools", value=True)
        send_clicked = st.form_submit_button("Send to session")
        if send_clicked:
            payload = {"message": message.strip(), "use_tools": allow_tools}
            if not payload["message"]:
                st.warning("Message cannot be empty.")
            else:
                response = call_api("POST", f"/chat/sessions/{active_session}/messages", json=payload)
                if isinstance(response, dict):
                    reply = response.get("reply", "")
                    tools = response.get("tools") or []
                    if reply:
                        st.success(f"Assistant replied: {reply}")
                    if tools:
                        st.info(f"Tools used: {', '.join(tools)}")
                    refresh_history(active_session)


def main():
    st.set_page_config(page_title="PT Assistant Demo", layout="wide")
    init_state()

    st.title("PT Assistant API Demo")

    tabs = st.tabs(["Users", "Sessions", "Chat"])
    with tabs[0]:
        render_users_tab()
    with tabs[1]:
        render_sessions_tab()
    with tabs[2]:
        render_chat_tab()


if __name__ == "__main__":
    main()
