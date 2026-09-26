"""Vercel serverless entry point for the NextStep Prompt Inspector.

Vercel's @vercel/python builder statically scans for a top-level `app` --
so the import MUST be at true module top-level, not inside try/except.
"""
import sys
from pathlib import Path

_here = Path(__file__).resolve().parent          # /var/task/api
_root = _here.parent                              # /var/task
for _cand in [str(_root), str(_here), "/var/task"]:
    if _cand not in sys.path:
        sys.path.insert(0, _cand)

from server import app  # noqa: E402,F401
