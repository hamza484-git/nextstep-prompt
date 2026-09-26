"""Small FastAPI wrapper that exposes the reasoning layer + serves the
inspector dashboard.

Run:
    pip install -r requirements.txt   # already has fastapi, uvicorn will be added
    python -m uvicorn api:app --port 8100 --reload

Then open http://localhost:8100/
"""
from __future__ import annotations
import json
from pathlib import Path
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from nextstep_prompt.reason import reason, PROMPT_VERSION
from nextstep_prompt.prompts import SYSTEM_V3, SCHEMA_HINT_V3


app = FastAPI(title="NextStep Prompt Inspector", version="1.0.0")
app.add_middleware(
    CORSMiddleware, allow_origins=["*"], allow_credentials=False,
    allow_methods=["*"], allow_headers=["*"],
)


class ReasonIn(BaseModel):
    text: str


@app.get("/api/health")
def health():
    from nextstep_prompt.llm import get_provider
    p = get_provider()
    return {"ok": True, "provider": p.name, "model": getattr(p, "model", "?"),
            "prompt_version": PROMPT_VERSION}


@app.get("/api/prompt")
def get_prompt():
    """Return the actual system prompt and schema hint for the inspector."""
    return {
        "version": PROMPT_VERSION,
        "system_prompt": SYSTEM_V3,
        "schema_hint": SCHEMA_HINT_V3,
    }


@app.post("/api/reason")
def do_reason(body: ReasonIn):
    r = reason(body.text)
    if not r.ok or r.assessment is None:
        return {"ok": False, "error": r.error,
                "preprocess_notes": r.preprocess_notes}
    return {
        "ok": True,
        "assessment": r.assessment.model_dump(mode="json"),
        "preprocess_notes": r.preprocess_notes,
        "uncertainty_breakdown": r.uncertainty_breakdown,
        "lint_report": {
            "ok": r.lint_report.ok,
            "invented_facts": r.lint_report.invented_facts,
            "stale_missing_info": r.lint_report.stale_missing_info,
        } if r.lint_report else None,
        "llm": {
            "model": r.llm.model, "latency_ms": r.llm.latency_ms,
            "repair_attempts": r.llm.repair_attempts,
        } if r.llm else None,
    }


@app.get("/api/eval-report")
def get_eval_report(kind: str = "mock"):
    """Return the eval report as JSON so the dashboard can render it."""
    path = Path(__file__).parent / "evals" / (
        "report_gemini.md" if kind == "gemini" else "report.md")
    if not path.exists():
        return {"exists": False}
    return {"exists": True, "markdown": path.read_text(encoding="utf-8"),
            "kind": kind}


# Serve the static dashboard from /web
_here = Path(__file__).parent
app.mount("/", StaticFiles(directory=str(_here / "web"), html=True), name="web")
