"""Anti-hallucination linter.

Runs AFTER the model returns. Its job is to catch invented facts.

Two kinds of checks:
  1. Named-entity check: any date, time, amount, or proper noun in the
     assessment text that does NOT appear in the input text is flagged.
  2. Structural check: certain fields (like `missing_info`) must not be
     silently populated with values that ARE present in the input — the
     model sometimes lists "amount" as missing when the user said "5000".

The linter cannot fix the assessment; it produces a `LintReport` that the
caller can either surface to the user, retry the model with, or use as a
pass/fail gate in the eval harness.
"""
from __future__ import annotations
import re
from dataclasses import dataclass, field


_MONEY = re.compile(r"(?:₹|rs\.?|inr|\$|usd)\s*\d[\d,]*", re.IGNORECASE)
_TIME = re.compile(r"\b\d{1,2}[:.]\d{2}\s*(?:am|pm)?\b", re.IGNORECASE)
_DATE = re.compile(r"\b(?:\d{1,2}[-/]\d{1,2}(?:[-/]\d{2,4})?|"
                   r"(?:jan|feb|mar|apr|may|jun|jul|aug|sep|oct|nov|dec)\w*\s+\d{1,2})\b",
                   re.IGNORECASE)
_WEEKDAY = re.compile(r"\b(monday|tuesday|wednesday|thursday|friday|saturday|sunday)\b",
                      re.IGNORECASE)


@dataclass
class LintReport:
    ok: bool
    invented_facts: list[str] = field(default_factory=list)
    stale_missing_info: list[str] = field(default_factory=list)
    notes: list[str] = field(default_factory=list)


def _extract(text: str) -> set[str]:
    found: set[str] = set()
    for r in (_MONEY, _TIME, _DATE, _WEEKDAY):
        for m in r.finditer(text):
            found.add(m.group(0).lower())
    return found


def lint(input_text: str, assessment: dict) -> LintReport:
    src = _extract(input_text)
    # concatenate every free-text field the assessment produced
    out_bits = [assessment.get("summary", "") or "",
                assessment.get("notes_to_user", "") or ""]
    for p in assessment.get("priorities", []) or []:
        for k in ("title", "why", "action"):
            v = p.get(k)
            if v: out_bits.append(v)
    out_text = "\n".join(out_bits)
    out = _extract(out_text)

    invented = sorted(out - src)

    # stale missing_info: item claims something is missing that is present
    stale: list[str] = []
    lowered_in = input_text.lower()
    for item in assessment.get("missing_info", []) or []:
        low = item.lower()
        for keyword in ("amount", "deadline", "date", "time", "name"):
            if keyword in low:
                # is the concept present in the input?
                if keyword == "amount" and _MONEY.search(lowered_in):
                    stale.append(item); break
                if keyword in ("deadline", "date") and (_DATE.search(lowered_in) or _WEEKDAY.search(lowered_in)):
                    stale.append(item); break
                if keyword == "time" and _TIME.search(lowered_in):
                    stale.append(item); break

    return LintReport(
        ok=not invented and not stale,
        invented_facts=invented,
        stale_missing_info=stale,
    )
