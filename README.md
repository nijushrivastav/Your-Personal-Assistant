# Personal Assistant (multi-user)

Python rewrite of the n8n "Personal Assistant" workflow. Same Gemini agent, same system
prompt (`sysprompt.md`), same 15-turn memory, same tools, but every person signs in with
their **own** Google account, so the assistant only touches their own data.

| n8n piece | Now |
|---|---|
| Webhook + AI Agent + Gemini | `agent.py` (google-genai, automatic tool calling) |
| 15 Google tools, SerpApi, Calculator | `tools.py` (names match `sysprompt.md`) |
| Your Google credentials in n8n | `auth.py` (Google sign-in per user) |
| Streamlit page → webhook | `app.py` calls the agent directly |

Your old files are untouched: `app_n8n.py` is your original Streamlit app, and the n8n
workflow still works as a backup.

## Your existing data

All your calendar, Gmail, Tasks and Docs data lives in your Google account, so signing in
with that same account shows it all. For expenses, set `OWNER_EMAIL` (your Google email) and
`OWNER_EXPENSE_SHEET_ID` (the ID from your sheet's URL) and the assistant keeps writing to
your existing "Expense Tracking" sheet. Other users automatically get their own
"Expense Tracking (Personal Assistant)" sheet, created the first time they log an expense.

Tasks use each user's default Google Tasks list.

## 1. Google Cloud setup (one time)

1. Create a project at https://console.cloud.google.com.
2. **APIs & Services → Library**: enable Gmail API, Google Calendar API, Google Tasks API,
   Google Docs API, Google Sheets API, Google Drive API.
3. **OAuth consent screen**: user type *External*, publishing status *Testing*. Add every
   friend/family Gmail address under **Test users** (limit 100).
4. **Credentials → Create credentials → OAuth client ID → Web application**. Add authorized
   redirect URIs: `http://localhost:8501` (local) and later your deployed URL.
5. Copy the client ID and secret.

While in Testing mode Google shows an "unverified app" warning (Advanced → Continue) and
refresh tokens expire after 7 days, so users may need to sign in again weekly. Going fully
public requires Google's app verification, which is stricter for Gmail scopes.

## 2. Run locally

```bash
cp .env.example .env        # fill in the keys
uv sync                     # installs dependencies, refreshes uv.lock
uv run streamlit run app.py
```

## 3. Deploy (Streamlit Community Cloud)

1. Push this folder to GitHub (`.env` is git-ignored).
2. Create the app at https://share.streamlit.io, main file `app.py`.
3. Paste the contents of `.streamlit/secrets.toml.example` (filled in) into **Secrets**,
   with `APP_URL` set to your real app URL.
4. Add that same URL as an authorized redirect URI in Google Cloud.

## Things to know

- Your `GEMINI_API_KEY` and `SERPAPI_API_KEY` pay for everyone's usage. Use `ALLOWED_EMAILS`
  to restrict the app to people you trust.
- Chat memory lives in the browser session; refreshing the page signs the user out and clears it.
- Deleting is still protected by the system prompt ("confirm destructive actions").
