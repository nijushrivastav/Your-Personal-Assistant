"""Per-user Google sign-in (OAuth 2.0 web flow) for Streamlit.

Every visitor signs in with their own Google account, so the agent's tools
(Calendar, Gmail, Tasks, Docs, Sheets) always act on THAT user's data only.
"""
import os

import streamlit as st
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import Flow
from googleapiclient.discovery import build

import config

SCOPES = [
    "openid",
    "https://www.googleapis.com/auth/userinfo.email",
    "https://www.googleapis.com/auth/userinfo.profile",
    "https://www.googleapis.com/auth/calendar",
    "https://www.googleapis.com/auth/gmail.readonly",
    "https://www.googleapis.com/auth/gmail.send",
    "https://www.googleapis.com/auth/tasks",
    "https://www.googleapis.com/auth/documents",
    "https://www.googleapis.com/auth/spreadsheets",
    "https://www.googleapis.com/auth/drive.file",
]

# Google may return extra previously-granted scopes; don't treat that as an error.
os.environ["OAUTHLIB_RELAX_TOKEN_SCOPE"] = "1"
if config.get("APP_URL", "http://localhost:8501").startswith("http://localhost"):
    os.environ["OAUTHLIB_INSECURE_TRANSPORT"] = "1"  # local development only


@st.cache_resource
def _pending() -> dict:
    """state -> PKCE code_verifier, shared across sessions of this server process."""
    return {}


def _make_flow() -> Flow:
    client_config = {
        "web": {
            "client_id": config.get("GOOGLE_CLIENT_ID"),
            "client_secret": config.get("GOOGLE_CLIENT_SECRET"),
            "auth_uri": "https://accounts.google.com/o/oauth2/auth",
            "token_uri": "https://oauth2.googleapis.com/token",
        }
    }
    return Flow.from_client_config(
        client_config,
        scopes=SCOPES,
        redirect_uri=config.get("APP_URL", "http://localhost:8501"),
    )


def login_url() -> str:
    flow = _make_flow()
    url, state = flow.authorization_url(
        access_type="offline", prompt="consent", include_granted_scopes="true"
    )
    pending = _pending()
    if len(pending) > 500:  # keep the dict from growing forever
        pending.pop(next(iter(pending)))
    pending[state] = flow.code_verifier
    return url


def _finish_login(code: str, state: str) -> None:
    pending = _pending()
    if state not in pending:
        st.session_state["auth_error"] = "Login session expired. Please try signing in again."
        return
    flow = _make_flow()
    flow.code_verifier = pending.pop(state)
    flow.fetch_token(code=code)
    creds = flow.credentials
    info = build("oauth2", "v2", credentials=creds, cache_discovery=False).userinfo().get().execute()
    st.session_state["creds"] = creds
    st.session_state["user"] = {"email": info.get("email", ""), "name": info.get("name", "")}


def handle_callback() -> None:
    """Call at the top of the app: completes login if Google just redirected back."""
    params = st.query_params
    if "code" in params and "state" in params and "creds" not in st.session_state:
        try:
            _finish_login(params["code"], params["state"])
        except Exception as e:  # noqa: BLE001
            st.session_state["auth_error"] = f"Google sign-in failed: {e}"
        st.query_params.clear()
        st.rerun()
    elif "error" in params:
        st.session_state["auth_error"] = f"Google sign-in was cancelled ({params['error']})."
        st.query_params.clear()
        st.rerun()


def current_user() -> dict | None:
    return st.session_state.get("user")


def get_credentials() -> Credentials | None:
    return st.session_state.get("creds")


def sign_out() -> None:
    for key in ("creds", "user", "messages", "timezone"):
        st.session_state.pop(key, None)
