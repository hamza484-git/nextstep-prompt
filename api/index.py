"""Vercel serverless entry point for the NextStep Prompt Inspector.

Re-exports the FastAPI `app` from server.py. Vercel Python auto-detects it
as an ASGI callable and wraps it into a serverless function.

Local run (uvicorn):  python -m uvicorn server:app --port 8100
Vercel run:           this file is invoked per-request via @vercel/python
"""
import sys
from pathlib import Path

# Vercel bundle layout puts this at /var/task/api/index.py; parent is repo root.
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from server import app  # noqa: E402,F401
