"""Gemini agent: same system prompt, model and 15-turn memory as the n8n workflow."""
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

from google import genai
from google.genai import types

import config

SYSTEM_PROMPT = (Path(__file__).parent / "sysprompt.md").read_text(encoding="utf-8")
MEMORY_WINDOW = 15  # conversation turns remembered (same as n8n's Simple Memory)


def run_agent(user_message: str, history: list[dict], tools: list, email: str, tz: str) -> str:
    now = datetime.now(ZoneInfo(tz))
    context = (
        "\n\nCURRENT CONTEXT\n"
        f"Today is {now:%A, %d %B %Y}, local time {now:%H:%M} ({tz}).\n"
        f"Signed-in user: {email}. Resolve relative dates like 'tomorrow' or 'next Monday' "
        "from today's date above."
    )

    contents = [
        types.Content(
            role="user" if m["role"] == "user" else "model",
            parts=[types.Part(text=m["content"])],
        )
        for m in history[-MEMORY_WINDOW * 2 :]
    ]
    contents.append(types.Content(role="user", parts=[types.Part(text=user_message)]))

    client = genai.Client(api_key=config.get("GEMINI_API_KEY"))
    response = client.models.generate_content(
        model=config.get("GEMINI_MODEL", "gemini-3.5-flash-lite"),
        contents=contents,
        config=types.GenerateContentConfig(
            system_instruction=SYSTEM_PROMPT + context,
            tools=tools,
            automatic_function_calling=types.AutomaticFunctionCallingConfig(
                maximum_remote_calls=12
            ),
        ),
    )
    return response.text or "Done."
