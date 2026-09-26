"""Preprocessing done BEFORE the reasoning prompt.

Four passes:
  1. Injection quarantine — wrap user text so the model treats it as data.
  2. Long-input distillation — a 4000-word paste with 2 relevant lines gets
     compressed to a short "distilled brief" the model actually attends to.
     This directly addresses the blocker.
  3. Time normalisation — resolve "tomorrow", "by Friday", "in 3 days" using
     the server clock. The reasoning prompt receives ISO timestamps, not
     natural-language dates, so the model cannot misdate the situation.
  4. Contradiction spotter — cheap regex layer, flags pairs the model tends
     to gloss over.

None of these depend on the LLM. That is intentional: preprocessing is where
you save both cost and correctness. A worse LLM after good preprocessing beats
a better LLM given raw text.
"""
from __future__ import annotations
import re
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone


# ---------------- 1. injection quarantine -----------------------------------
_INJECTION = [
    r"ignore (all |your |previous |prior )?(instructions?|prompts?|rules?)",
    r"disregard (all |your |previous |prior )?(instructions?|prompts?)",
    r"system\s*[:>]\s*",
    r"you are now",
    r"new (instructions?|role|rules?):",
    r"share your (upi|pin|password|otp|api key|token)",
    r"tell (the user|them) (that|to)",
    r"pretend (to be|you are)",
]


def quarantine(text: str) -> tuple[str, list[str]]:
    hits = [p for p in _INJECTION if re.search(p, text.lower())]
    escaped = text.replace("</user_input>", "</user_input​>")  # zero-width space
    return (
        '<user_input source="paste_or_type" trust="data_only">\n'
        + escaped + "\n</user_input>",
        hits,
    )


# ---------------- 2. long-input distillation --------------------------------
# Strategy: if the input is >600 words, keep:
#   - the first 3 lines (user's typed opener, usually the ask)
#   - the last 8 lines (the newest content in a WhatsApp export)
#   - any line matching a "signal regex" (times, money, deadlines, feelings)
#   - a running marker showing what we dropped
_SIGNAL_PATTERNS = [
    r"\b(deadline|due|submit|exam|viva|interview|hearing|meeting)\b",
    r"\b(₹|rs\.?|rupees|inr|\$|usd|eur)\s*\d",
    r"\b(tomorrow|today|tonight|yesterday|monday|tuesday|wednesday|thursday|friday|saturday|sunday)\b",
    r"\b(hospital|admitted|emergency|urgent|police|fired|dumped|broke up)\b",
    r"\b(can'?t|won'?t|refuse|blocked|stuck|out of time)\b",
    r"\b(hopeless|worthless|tired of|point|give up|no more)\b",
    r"\b\d{1,2}[:.]\d{2}\b",   # times
    r"\b\d{1,2}[-/]\d{1,2}(?:[-/]\d{2,4})?\b",  # dates
]


@dataclass
class Distilled:
    original_word_count: int
    kept_word_count: int
    text: str
    dropped_summary: str


def distill(text: str, max_words: int = 400) -> Distilled:
    words = text.split()
    if len(words) <= max_words:
        return Distilled(len(words), len(words), text, "")
    lines = [l for l in text.splitlines() if l.strip()]
    n = len(lines)
    head_idx = set(range(min(3, n)))
    tail_idx = set(range(max(0, n - 8), n))
    signal_idx: set[int] = set()
    for i, l in enumerate(lines):
        low = l.lower()
        if any(re.search(p, low) for p in _SIGNAL_PATTERNS):
            signal_idx.add(i)
    keep_idx = sorted(head_idx | tail_idx | signal_idx)
    keep_order = [(i, lines[i]) for i in keep_idx]
    kept_text = "\n".join(l for _, l in keep_order)
    dropped = len(lines) - len(keep_order)
    return Distilled(
        original_word_count=len(words),
        kept_word_count=len(kept_text.split()),
        text=kept_text,
        dropped_summary=f"[distillation dropped {dropped} of {len(lines)} lines "
                        f"({len(words)}→{len(kept_text.split())} words). "
                        "kept: opener, latest 8 lines, any line naming a deadline, "
                        "money, time, or emotional signal.]",
    )


# ---------------- 3. time normalisation --------------------------------------
_WEEKDAYS = ["monday", "tuesday", "wednesday", "thursday", "friday", "saturday", "sunday"]


@dataclass
class TimeContext:
    now_iso: str
    day_of_week: str
    normalised: dict[str, str] = field(default_factory=dict)


def normalise_times(text: str, now: datetime | None = None) -> TimeContext:
    """Extract relative-time mentions and resolve to absolute ISO strings.
    Does NOT modify the original text — the model sees `time_context` as
    structured metadata alongside the raw text."""
    now = now or datetime.now(timezone.utc)
    lowered = text.lower()
    out: dict[str, str] = {}
    if re.search(r"\btonight\b", lowered):
        end = now.replace(hour=23, minute=59, second=0, microsecond=0)
        out["tonight_end"] = end.isoformat()
    if re.search(r"\btomorrow\b", lowered):
        tmr = (now + timedelta(days=1)).replace(hour=0, minute=0, second=0, microsecond=0)
        out["tomorrow_start"] = tmr.isoformat()
    if re.search(r"\btoday\b", lowered):
        out["today_start"] = now.replace(hour=0, minute=0, second=0, microsecond=0).isoformat()
    for i, day in enumerate(_WEEKDAYS):
        if re.search(rf"\b(by |on )?{day}\b", lowered):
            days_ahead = (i - now.weekday()) % 7
            if days_ahead == 0:
                out[f"{day}_note"] = "TODAY is " + day + " — 'by " + day + "' may mean end-of-today or next week"
                out[f"{day}_end_today"] = now.replace(hour=23, minute=59).isoformat()
            resolved = (now + timedelta(days=days_ahead or 7)).replace(hour=0, minute=0)
            out[f"next_{day}"] = resolved.isoformat()
    return TimeContext(
        now_iso=now.isoformat(),
        day_of_week=_WEEKDAYS[now.weekday()],
        normalised=out,
    )


# ---------------- 4. contradiction spotter ----------------------------------
_CONTRADICTIONS = [
    (r"no (money|savings|cash|paise)", r"(book|buy|pay|afford|flight|udhaar)"),
    (r"friday", r"thursday"),
    (r"can'?t (make|do|attend|come)", r"(will|going to|planning to) (attend|do|make|come)"),
    (r"not (really |fully |quite )?talking", r"borrow|ask|message"),
]


def spot_contradictions(text: str) -> list[str]:
    t = text.lower()
    out: list[str] = []
    for a, b in _CONTRADICTIONS:
        if re.search(a, t) and re.search(b, t):
            out.append(f"{a}  <->  {b}")
    return out


# ---------------- aggregator -------------------------------------------------
@dataclass
class Preprocessed:
    quarantined_text: str
    injection_hits: list[str]
    distilled: Distilled
    time_context: TimeContext
    contradictions: list[str]


def preprocess(text: str, now: datetime | None = None) -> Preprocessed:
    dist = distill(text)
    q, hits = quarantine(dist.text)
    return Preprocessed(
        quarantined_text=q,
        injection_hits=hits,
        distilled=dist,
        time_context=normalise_times(text, now=now),
        contradictions=spot_contradictions(text),
    )
