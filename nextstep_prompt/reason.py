"""The reasoning layer. `reason(text) -> Assessment` is the whole public API."""
from __future__ import annotations
import json
from dataclasses import dataclass, field
from datetime import datetime
from .preprocess import preprocess
from .prompts import SYSTEM_V3, SCHEMA_HINT_V3, build_user_block
from .llm import get_provider, LLMProvider, LLMResult
from .uncertainty import compute as compute_uncertainty
from .linter import lint, LintReport
from .schema import Assessment, Priority, RiskFlag


@dataclass
class ReasoningResult:
    assessment: Assessment | None
    llm: LLMResult | None
    lint_report: LintReport | None
    uncertainty_breakdown: dict[str, float] = field(default_factory=dict)
    ensemble_top_ids: list[str] = field(default_factory=list)
    preprocess_notes: dict = field(default_factory=dict)
    ok: bool = False
    error: str | None = None


PROMPT_VERSION = "v3"


def reason(text: str, situation_id: str = "sit_1",
           provider: LLMProvider | None = None,
           now: datetime | None = None,
           ensemble_samples: int = 1) -> ReasoningResult:
    provider = provider or get_provider()

    # 1) preprocess
    pp = preprocess(text, now=now)

    # 2) build user block (raw text + time_context + contradictions block)
    time_ctx = {
        "now_iso": pp.time_context.now_iso,
        "day_of_week": pp.time_context.day_of_week,
        "normalised": pp.time_context.normalised,
    }
    user_block = build_user_block(
        preprocessed_text=pp.quarantined_text,
        time_context=time_ctx,
        distillation_note=pp.distilled.dropped_summary,
        contradictions=pp.contradictions,
    )

    # 3) LLM call (with 1 repair attempt on invalid JSON)
    res = provider.complete_json(SYSTEM_V3, user_block, SCHEMA_HINT_V3, temperature=0.0)
    if not res.ok:
        res = provider.complete_json(
            SYSTEM_V3,
            user_block + "\n\nYour previous output was invalid JSON. Return ONLY JSON matching the schema.",
            SCHEMA_HINT_V3, temperature=0.0)
    if not res.ok or res.data is None:
        return ReasoningResult(None, res, None, ok=False, error="unparseable_json",
                               preprocess_notes=_pp_notes(pp))

    data = res.data

    # 4) build assessment
    try:
        priorities = [Priority(**p) for p in data.get("priorities", [])
                      if _priority_ok(p)]
        priorities = _mark_ties(priorities)
        flags = [RiskFlag(f) for f in data.get("risk_flags", []) if _valid_flag(f)]
        if pp.contradictions and RiskFlag.CONTRADICTION not in flags:
            flags.append(RiskFlag.CONTRADICTION)
        if pp.injection_hits and RiskFlag.PROMPT_INJECTION not in flags:
            flags.append(RiskFlag.PROMPT_INJECTION)
        a = Assessment(
            situation_id=situation_id,
            summary=data.get("summary", ""),
            urgency=data.get("urgency", "low"),
            constraints=data.get("constraints", []),
            dependencies=data.get("dependencies", []),
            missing_info=data.get("missing_info", []),
            priorities=priorities,
            risk_flags=flags,
            uncertainty=0.0,   # placeholder — recomputed next
            calm_mode=bool(data.get("calm_mode", False)),
            recovery_mode=bool(data.get("recovery_mode", False)),
            notes_to_user=data.get("notes_to_user"),
        )
    except Exception as e:
        return ReasoningResult(None, res, None, ok=False, error=f"schema:{e}",
                               preprocess_notes=_pp_notes(pp))

    # 5) ensemble sampling for stability signal (skipped if samples <= 1)
    ensemble_top_ids: list[str] = []
    if ensemble_samples > 1 and a.priorities:
        for _ in range(ensemble_samples - 1):
            r2 = provider.complete_json(SYSTEM_V3, user_block, SCHEMA_HINT_V3,
                                        temperature=0.3)
            if r2.ok and r2.data and r2.data.get("priorities"):
                # find rank-1 or lowest-rank id
                ps = r2.data["priorities"]
                top = min(ps, key=lambda p: p.get("rank", 99))
                ensemble_top_ids.append(top.get("id", "?"))
        # include our own top
        top_here = min(a.priorities, key=lambda p: p.rank)
        ensemble_top_ids.append(top_here.id)

    # 6) uncertainty
    unc, breakdown = compute_uncertainty(
        missing_info_count=len(a.missing_info),
        contradiction_flagged=any((f if isinstance(f, str) else f.value) == "contradiction"
                                   for f in a.risk_flags),
        priority_confidences=[p.confidence for p in a.priorities],
        ensemble_top_ids=ensemble_top_ids or None,
    )
    a.uncertainty = unc

    # 7) linter
    lint_report = lint(text, data)

    return ReasoningResult(
        assessment=a, llm=res, lint_report=lint_report,
        uncertainty_breakdown=breakdown, ensemble_top_ids=ensemble_top_ids,
        preprocess_notes=_pp_notes(pp), ok=True,
    )


def _pp_notes(pp) -> dict:
    return {
        "distillation": {
            "original_words": pp.distilled.original_word_count,
            "kept_words": pp.distilled.kept_word_count,
            "note": pp.distilled.dropped_summary,
        },
        "time_context": {
            "now_iso": pp.time_context.now_iso,
            "day_of_week": pp.time_context.day_of_week,
            "resolved": pp.time_context.normalised,
        },
        "contradictions": pp.contradictions,
        "injection_hits": pp.injection_hits,
    }


def _priority_ok(p: dict) -> bool:
    return isinstance(p, dict) and all(k in p for k in ("id", "title", "why", "rank"))


def _valid_flag(f: str) -> bool:
    try: RiskFlag(f); return True
    except ValueError: return False


def _mark_ties(ps: list[Priority]) -> list[Priority]:
    by_rank: dict[int, list[Priority]] = {}
    for p in ps: by_rank.setdefault(p.rank, []).append(p)
    for group in by_rank.values():
        if len(group) > 1:
            ids = [p.id for p in group]
            for p in group:
                p.tied_with = [i for i in ids if i != p.id]
    return ps
