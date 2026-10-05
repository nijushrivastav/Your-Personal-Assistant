"""The agent's tools: the same capabilities as the n8n workflow, built per signed-in user.

Tool names match the ones named in sysprompt.md. Docstrings and type hints are what
Gemini sees, so keep them clear.
"""
import ast
import base64
import operator
import re
import uuid
from datetime import datetime
from email.message import EmailMessage
from functools import wraps
from zoneinfo import ZoneInfo

import requests
from googleapiclient.discovery import build
from googleapiclient.errors import HttpError

import config

EXPENSE_SHEET_NAME = "Expense Tracking (Personal Assistant)"
EXPENSE_HEADERS = ["ID", "Date", "Expense_Category", "Expense"]


# ---------------------------------------------------------------- helpers
def _safe(fn):
    """Return errors as text so the model can explain them instead of crashing the app."""

    @wraps(fn)
    def inner(*args, **kwargs):
        try:
            return fn(*args, **kwargs)
        except HttpError as e:
            return f"Error: Google API request failed ({e.resp.status}): {str(e)[:300]}"
        except Exception as e:  # noqa: BLE001
            return f"Error: {type(e).__name__}: {e}"

    return inner


def _rfc3339(value: str, tz: str) -> str:
    dt = datetime.fromisoformat(value.strip().replace("Z", "+00:00"))
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=ZoneInfo(tz))
    return dt.isoformat()


def _doc_id(value: str) -> str:
    m = re.search(r"/d/([\w-]+)", value)
    return m.group(1) if m else value.strip()


def _walk_body(part: dict, mime: str) -> str:
    if part.get("mimeType") == mime and part.get("body", {}).get("data"):
        return base64.urlsafe_b64decode(part["body"]["data"]).decode("utf-8", "replace")
    for sub in part.get("parts", []) or []:
        found = _walk_body(sub, mime)
        if found:
            return found
    return ""


def _message_text(payload: dict) -> str:
    text = _walk_body(payload, "text/plain")
    if not text:
        html = _walk_body(payload, "text/html")
        text = re.sub(r"<[^>]+>", " ", html)
    return re.sub(r"\s+", " ", text).strip()


def _headers(payload: dict) -> dict:
    return {h["name"].lower(): h["value"] for h in payload.get("headers", [])}


# ------------------------------------------------------- user-less tools
_OPS = {
    ast.Add: operator.add,
    ast.Sub: operator.sub,
    ast.Mult: operator.mul,
    ast.Div: operator.truediv,
    ast.Mod: operator.mod,
    ast.FloorDiv: operator.floordiv,
    ast.Pow: operator.pow,
    ast.USub: operator.neg,
    ast.UAdd: operator.pos,
}


def _eval(node):
    if isinstance(node, ast.Constant) and isinstance(node.value, (int, float)):
        return node.value
    if isinstance(node, ast.BinOp) and type(node.op) in _OPS:
        left, right = _eval(node.left), _eval(node.right)
        if isinstance(node.op, ast.Pow) and abs(right) > 100:
            raise ValueError("exponent too large")
        return _OPS[type(node.op)](left, right)
    if isinstance(node, ast.UnaryOp) and type(node.op) in _OPS:
        return _OPS[type(node.op)](_eval(node.operand))
    raise ValueError("unsupported expression")


@_safe
def Calculator(expression: str) -> str:
    """Evaluate an arithmetic expression, e.g. '250 + 399.5 + 120' or '(1200 * 0.18) / 4'.
    Use this for every total, average or budget calculation."""
    result = _eval(ast.parse(expression.strip(), mode="eval").body)
    return str(round(result, 10))


@_safe
def Google_Search(query: str) -> str:
    """Search Google for current or external information (news, facts, prices).
    Never use it for the user's personal data such as emails, calendar or tasks."""
    key = config.get("SERPAPI_API_KEY")
    if not key:
        return "Web search is not configured on this server."
    r = requests.get(
        "https://serpapi.com/search.json",
        params={"engine": "google", "q": query, "gl": "in", "num": 5, "api_key": key},
        timeout=20,
    )
    r.raise_for_status()
    data = r.json()
    out = {}
    box = data.get("answer_box")
    if box:
        out["answer_box"] = {k: box[k] for k in ("title", "answer", "snippet") if k in box}
    out["results"] = [
        {"title": o.get("title"), "link": o.get("link"), "snippet": o.get("snippet")}
        for o in data.get("organic_results", [])[:5]
    ]
    return str(out)


# ------------------------------------------------------------ user tools
def get_user_timezone(creds) -> str:
    try:
        cal = build("calendar", "v3", credentials=creds, cache_discovery=False)
        return cal.calendars().get(calendarId="primary").execute()["timeZone"]
    except Exception:  # noqa: BLE001
        return config.get("DEFAULT_TIMEZONE", "Asia/Kolkata")


def _resolve_expense_sheet(creds, email: str) -> str:
    """Owner keeps their existing sheet; everyone else gets (or already has) their own."""
    owner = config.get("OWNER_EMAIL").strip().lower()
    owner_sheet = config.get("OWNER_EXPENSE_SHEET_ID").strip()
    if owner and owner_sheet and email.lower() == owner:
        return owner_sheet

    drive = build("drive", "v3", credentials=creds, cache_discovery=False)
    found = (
        drive.files()
        .list(
            q=f"name='{EXPENSE_SHEET_NAME}' and trashed=false "
            "and mimeType='application/vnd.google-apps.spreadsheet'",
            fields="files(id)",
            pageSize=1,
        )
        .execute()
        .get("files", [])
    )
    if found:
        return found[0]["id"]

    sheets = build("sheets", "v4", credentials=creds, cache_discovery=False)
    sid = sheets.spreadsheets().create(body={"properties": {"title": EXPENSE_SHEET_NAME}}).execute()[
        "spreadsheetId"
    ]
    sheets.spreadsheets().values().append(
        spreadsheetId=sid,
        range="A1",
        valueInputOption="USER_ENTERED",
        body={"values": [EXPENSE_HEADERS]},
    ).execute()
    return sid


def build_tools(creds, email: str, tz: str) -> list:
    """Create the tool functions bound to this user's Google credentials."""
    cache: dict = {}

    def svc(name: str, version: str):
        return build(name, version, credentials=creds, cache_discovery=False)

    def expense_sheet() -> str:
        if "sheet" not in cache:
            cache["sheet"] = _resolve_expense_sheet(creds, email)
        return cache["sheet"]

    # ---- Calendar
    @_safe
    def Create_Calendar_Event(title: str, start: str, end: str, description: str = "") -> str:
        """Create a single Google Calendar event.
        start and end are ISO 8601 date-times such as '2026-10-08T15:00:00' (user's local time)."""
        body = {
            "summary": title,
            "description": description,
            "start": {"dateTime": _rfc3339(start, tz), "timeZone": tz},
            "end": {"dateTime": _rfc3339(end, tz), "timeZone": tz},
        }
        ev = svc("calendar", "v3").events().insert(calendarId="primary", body=body).execute()
        return f"Created event '{title}' (id {ev['id']}): {ev.get('htmlLink', '')}"

    @_safe
    def Get_Single_Calendar_Event(event_id: str) -> str:
        """Fetch the details of one calendar event by its event ID."""
        ev = svc("calendar", "v3").events().get(calendarId="primary", eventId=event_id).execute()
        return str(
            {
                k: ev.get(k)
                for k in ("id", "summary", "description", "location", "start", "end", "attendees")
            }
        )

    @_safe
    def Get_Calendar_Events(after: str, before: str) -> str:
        """Fetch calendar events between two ISO 8601 date-times (e.g. today's meetings,
        this week's events). after = start of range, before = end of range."""
        res = (
            svc("calendar", "v3")
            .events()
            .list(
                calendarId="primary",
                timeMin=_rfc3339(after, tz),
                timeMax=_rfc3339(before, tz),
                singleEvents=True,
                orderBy="startTime",
                maxResults=50,
            )
            .execute()
        )
        events = [
            {
                "id": e["id"],
                "title": e.get("summary", "(no title)"),
                "start": e["start"].get("dateTime", e["start"].get("date")),
                "end": e["end"].get("dateTime", e["end"].get("date")),
                "location": e.get("location", ""),
            }
            for e in res.get("items", [])
        ]
        return str(events) if events else "No events found in that range."

    # ---- Gmail
    @_safe
    def Get_Messages_Gmail(limit: int = 5, query: str = "") -> str:
        """Fetch recent emails from the inbox (max 15). Optional Gmail search query,
        e.g. 'from:boss@example.com' or 'is:unread'. Returns sender, subject, date, text."""
        gmail = svc("gmail", "v1")
        refs = (
            gmail.users()
            .messages()
            .list(userId="me", labelIds=["INBOX"], q=query, maxResults=max(1, min(limit, 15)))
            .execute()
            .get("messages", [])
        )
        out = []
        for ref in refs:
            m = gmail.users().messages().get(userId="me", id=ref["id"], format="full").execute()
            h = _headers(m["payload"])
            out.append(
                {
                    "id": m["id"],
                    "thread_id": m["threadId"],
                    "from": h.get("from"),
                    "subject": h.get("subject"),
                    "date": h.get("date"),
                    "text": _message_text(m["payload"])[:1200],
                }
            )
        return str(out) if out else "No messages found."

    @_safe
    def Get_Single_Message_Gmail(message_id: str) -> str:
        """Fetch one email in full by its message ID."""
        m = svc("gmail", "v1").users().messages().get(userId="me", id=message_id, format="full").execute()
        h = _headers(m["payload"])
        return str(
            {
                "id": m["id"],
                "thread_id": m["threadId"],
                "from": h.get("from"),
                "to": h.get("to"),
                "subject": h.get("subject"),
                "date": h.get("date"),
                "text": _message_text(m["payload"])[:6000],
            }
        )

    @_safe
    def Send_Message_Gmail(to: str, subject: str, message: str, thread_id: str = "") -> str:
        """Send an email. To reply inside an existing conversation, pass that email's thread_id
        and use the subject 'Re: <original subject>'."""
        msg = EmailMessage()
        msg["To"] = to
        msg["Subject"] = subject
        msg.set_content(message)
        body = {"raw": base64.urlsafe_b64encode(msg.as_bytes()).decode()}
        if thread_id:
            body["threadId"] = thread_id
        sent = svc("gmail", "v1").users().messages().send(userId="me", body=body).execute()
        return f"Email sent to {to} (id {sent['id']})."

    # ---- Google Docs notes
    @_safe
    def Create_Notes_File(title: str) -> str:
        """Create a new, empty notes document (Google Doc) with the given title."""
        doc = svc("docs", "v1").documents().create(body={"title": title}).execute()
        did = doc["documentId"]
        return f"Created notes '{title}'. id={did} url=https://docs.google.com/document/d/{did}/edit"

    @_safe
    def Update_Notes(doc_id_or_url: str, text: str) -> str:
        """Append text to the END of an existing notes document. Never overwrites."""
        docs = svc("docs", "v1")
        did = _doc_id(doc_id_or_url)
        doc = docs.documents().get(documentId=did).execute()
        end = doc["body"]["content"][-1]["endIndex"]
        insert = text if end <= 2 else "\n" + text
        docs.documents().batchUpdate(
            documentId=did,
            body={"requests": [{"insertText": {"location": {"index": end - 1}, "text": insert}}]},
        ).execute()
        return "Notes updated."

    @_safe
    def Get_Notes(doc_id_or_url: str) -> str:
        """Read the text content of a notes document."""
        doc = svc("docs", "v1").documents().get(documentId=_doc_id(doc_id_or_url)).execute()
        parts = []
        for el in doc["body"]["content"]:
            for run in el.get("paragraph", {}).get("elements", []):
                parts.append(run.get("textRun", {}).get("content", ""))
        text = "".join(parts).strip()
        return f"{doc.get('title', '')}\n{text[:8000]}" if text else "The document is empty."

    # ---- Google Tasks
    @_safe
    def Create_Tasks(title: str, notes: str = "") -> str:
        """Create a new task in the user's to-do list."""
        t = svc("tasks", "v1").tasks().insert(tasklist="@default", body={"title": title, "notes": notes}).execute()
        return f"Created task '{title}' (id {t['id']})."

    @_safe
    def Get_Single_Task(task_id: str) -> str:
        """Read one task by its task ID."""
        t = svc("tasks", "v1").tasks().get(tasklist="@default", task=task_id).execute()
        return str({k: t.get(k) for k in ("id", "title", "notes", "status", "due")})

    @_safe
    def Get_Multiple_Tasks(show_completed: bool = False) -> str:
        """List the user's tasks with their IDs. Call this first when you need a task ID."""
        res = (
            svc("tasks", "v1")
            .tasks()
            .list(tasklist="@default", showCompleted=show_completed, maxResults=100)
            .execute()
        )
        tasks = [
            {"id": t["id"], "title": t.get("title", ""), "status": t.get("status"), "due": t.get("due")}
            for t in res.get("items", [])
        ]
        return str(tasks) if tasks else "No tasks found."

    @_safe
    def Delete_Task(task_id: str) -> str:
        """Delete a task by ID. Only when the user explicitly asks or the task is clearly done."""
        svc("tasks", "v1").tasks().delete(tasklist="@default", task=task_id).execute()
        return "Task deleted."

    # ---- Expenses (Google Sheets)
    @_safe
    def Add_Expense(date: str, category: str, amount: float, expense_id: str = "") -> str:
        """Add one expense row. date like '2026-10-06', category like 'Food' or 'Travel',
        amount as a number. expense_id is optional (one is generated if empty)."""
        row = [expense_id or uuid.uuid4().hex[:8], date, category, amount]
        svc("sheets", "v4").spreadsheets().values().append(
            spreadsheetId=expense_sheet(),
            range="A:D",
            valueInputOption="USER_ENTERED",
            insertDataOption="INSERT_ROWS",
            body={"values": [row]},
        ).execute()
        return f"Added expense: {category} {amount} on {date}."

    @_safe
    def Get_Expenses() -> str:
        """Retrieve the expense history (ID, Date, Expense_Category, Expense). Use Calculator for totals."""
        rows = (
            svc("sheets", "v4")
            .spreadsheets()
            .values()
            .get(spreadsheetId=expense_sheet(), range="A:D")
            .execute()
            .get("values", [])
        )
        if len(rows) <= 1:
            return "No expenses recorded yet."
        head, data = rows[0], rows[1:][-300:]
        return str([dict(zip(head, r)) for r in data])

    return [
        Google_Search,
        Create_Calendar_Event,
        Get_Single_Calendar_Event,
        Get_Calendar_Events,
        Get_Messages_Gmail,
        Get_Single_Message_Gmail,
        Send_Message_Gmail,
        Create_Notes_File,
        Update_Notes,
        Get_Notes,
        Create_Tasks,
        Get_Single_Task,
        Get_Multiple_Tasks,
        Delete_Task,
        Calculator,
        Add_Expense,
        Get_Expenses,
    ]
