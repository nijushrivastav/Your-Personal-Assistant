# 🤝 Personal Assistant

An AI personal assistant that manages your **calendar, email, tasks, notes and expenses** through a simple chat interface. Built with **Gemini** and **Streamlit**, it works across multiple users: everyone signs in with their own Google account and the assistant only ever touches their own data.

It started as an [n8n](https://n8n.io) workflow and was rewritten in Python so it can be deployed and shared with friends and family.

## ✨ Features

| Area | What it can do |
|---|---|
| 💬 Q&A | Answer general questions, with live Google search (SerpApi) for current info |
| 📅 Calendar | Create events, look up a single event, list events for a day or week |
| ✉️ Gmail | Read and summarize emails, send new emails, reply in an existing thread |
| ✅ Tasks | Create, list, read and delete Google Tasks |
| 📝 Notes | Create Google Docs notes, append to them, read them back |
| 💸 Expenses | Log expenses to a Google Sheet, fetch history, calculate totals |

The agent understands relative dates ("tomorrow at 5pm", "next Monday"), remembers the last 15 turns of the conversation, and asks before deleting anything.

## 🧱 How it works

```
Streamlit chat UI  ──►  Gemini agent (automatic tool calling)  ──►  Google APIs
        ▲                         │                                 (Calendar, Gmail,
        │                         ▼                                  Tasks, Docs, Sheets)
 Google sign-in (OAuth)     SerpApi search, calculator
```

- **`app.py`**: Streamlit UI and chat loop
- **`auth.py`**: per-user Google OAuth sign-in
- **`agent.py`**: Gemini agent with the system prompt and conversation memory
- **`tools.py`**: the 17 tools the agent can call, bound to the signed-in user's credentials
- **`sysprompt.md`**: the agent's instructions
- **`app_n8n.py`**: the original frontend for the n8n version

## 🚀 Quick start

**Prerequisites:** Python 3.12+, [uv](https://docs.astral.sh/uv/), a Gemini API key, and a Google Cloud project.

1. **Google Cloud setup**
   - Enable the Gmail, Calendar, Tasks, Docs, Sheets and Drive APIs.
   - Configure the OAuth consent screen (External, Testing) and add yourself and your friends as test users.
   - Create an OAuth client of type **Web application** with the redirect URI `http://localhost:8501`.

2. **Configure**
   ```bash
   cp .env.example .env     # then fill in your keys
   ```

3. **Run**
   ```bash
   uv sync
   uv run streamlit run app.py
   ```

## ⚙️ Configuration

| Variable | Required | Description |
|---|---|---|
| `GEMINI_API_KEY` | ✅ | Google AI Studio API key |
| `GEMINI_MODEL` | | Model name (default `gemini-3.5-flash-lite`) |
| `GOOGLE_CLIENT_ID` / `GOOGLE_CLIENT_SECRET` | ✅ | OAuth web client credentials |
| `APP_URL` | ✅ | Public URL of the app; must match an authorized redirect URI |
| `SERPAPI_API_KEY` | | Enables web search |
| `ALLOWED_EMAILS` | | Comma-separated emails allowed to use the app (empty = any test user) |
| `OWNER_EMAIL`, `OWNER_EXPENSE_SHEET_ID` | | Keep using an existing expense sheet for the owner |
| `DEFAULT_TIMEZONE` | | Fallback timezone (default `Asia/Kolkata`) |

## ☁️ Deployment

- **Streamlit Community Cloud:** set the main file to `app.py`, paste the settings from `.streamlit/secrets.toml.example` into *Secrets*, and add the deployed URL as an authorized redirect URI in Google Cloud.
- **Render / Railway / Fly.io:** start command `streamlit run app.py --server.port $PORT --server.address 0.0.0.0`, with the same settings as environment variables.
- **Vercel is not supported**, since Streamlit needs a long-running server.

## 🔒 Privacy & security

- Each user authenticates with their own Google account; tool calls use that user's token only.
- No user data or tokens are stored on the server. Credentials and chat history live in the browser session and are cleared on sign-out or refresh.
- Never commit `.env` or `secrets.toml`; both are in `.gitignore`.
- Your Gemini and SerpApi keys are shared by all users, so use `ALLOWED_EMAILS` to limit access.

## ⚠️ Limitations

- While the Google OAuth app is in **Testing** mode, it is limited to 100 test users, shows an "unverified app" warning, and sign-ins expire after 7 days. A public launch requires Google's app verification (stricter for Gmail scopes).
- Chat memory is per browser session.

## 🗺️ Ideas for next steps

- Persistent chat history and "stay signed in"
- Confirmation buttons before sending emails or deleting tasks
- Voice input and a daily morning-brief summary
- Per-user usage limits

## 🛠️ Tech stack

Python · Streamlit · Google Gemini (`google-genai`) · Google Workspace APIs · OAuth 2.0 · SerpApi
