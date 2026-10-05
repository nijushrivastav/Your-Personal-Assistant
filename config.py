"""Central place to read settings from environment variables, .env, or Streamlit secrets."""
import os

from dotenv import load_dotenv

load_dotenv()


def get(name: str, default: str = "") -> str:
    value = os.getenv(name)
    if value:
        return value
    try:
        import streamlit as st

        return str(st.secrets.get(name, default))
    except Exception:
        return default
