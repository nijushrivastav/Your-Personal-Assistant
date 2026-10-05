import streamlit as st

import auth
import config
from agent import run_agent
from tools import build_tools, get_user_timezone

st.set_page_config(page_title="Your Personal Assistant", page_icon="🤝")

# Finish login if Google just redirected back to us.
auth.handle_callback()

# create the title for the page
st.title("🤝 Your Personal Assistant")

# add subheader
st.subheader("What can your personal assistant do?")

# create a list of what your assistant can do
st.markdown("""
            1. Answer questions on various topics.   
            2. Arrange Calendar events and meetings.  
            3. Read your emails and send replies, can even summarize them for you.
            4. Manage your tasks and to-do lists.
            5. Take quick notes for you.
            6. Track your expenses and budgeting.
            """)

user = auth.current_user()
creds = auth.get_credentials()

# ------------------------------------------------------------ signed out
if not user or not creds:
    if err := st.session_state.pop("auth_error", None):
        st.error(err)
    st.info(
        "Sign in with Google so the assistant can work with **your own** calendar, "
        "email, tasks, notes and expenses. Nobody else can see your data."
    )
    st.link_button("Sign in with Google", auth.login_url(), type="primary")
    st.caption(
        "While the app is in testing mode, Google may show an 'unverified app' screen: "
        "click **Advanced → Continue**."
    )
    st.stop()

# Optional allow-list so only friends/family can use your Gemini quota.
allowed = [e.strip().lower() for e in config.get("ALLOWED_EMAILS").split(",") if e.strip()]
if allowed and user["email"].lower() not in allowed:
    st.error(f"{user['email']} is not on the access list for this app.")
    if st.button("Sign out"):
        auth.sign_out()
        st.rerun()
    st.stop()

# -------------------------------------------------------------- sidebar
with st.sidebar:
    st.write(f"Signed in as **{user['name'] or user['email']}**")
    st.caption(user["email"])
    if st.button("Clear chat"):
        st.session_state.messages = []
        st.rerun()
    if st.button("Sign out"):
        auth.sign_out()
        st.rerun()

if "timezone" not in st.session_state:
    st.session_state.timezone = get_user_timezone(creds)

# add chats subheader
st.subheader("💬 Chat with your assistant")

# create a session state for message history
if "messages" not in st.session_state:
    st.session_state.messages = []

# show the messages in chat history
for message in st.session_state.messages:
    with st.chat_message(message["role"]):
        st.markdown(message["content"])

# create a chat input box
user_message = st.chat_input("Ask your assistant...")

# if user sends a message
if user_message:
    history = list(st.session_state.messages)
    st.session_state.messages.append({"role": "user", "content": user_message})
    with st.chat_message("user"):
        st.markdown(user_message)

    with st.chat_message("assistant"):
        with st.spinner("Working on it..."):
            try:
                tools = build_tools(creds, user["email"], st.session_state.timezone)
                ai_response = run_agent(
                    user_message, history, tools, user["email"], st.session_state.timezone
                )
            except Exception as e:  # noqa: BLE001
                ai_response = f"⚠️ Something went wrong: {e}"
        st.markdown(ai_response)
    st.session_state.messages.append({"role": "assistant", "content": ai_response})
