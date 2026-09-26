"""Signal-based uncertainty score. Deliberately NOT the model's self-rating.

Combines four signals into a [0,1] value:
  s_missing    -- how many missing_info fields did we surface?
  s_contradict -- did we detect a contradiction in the input?
  s_confidence -- average per-priority confidence (inverted)
  s_ensemble   -- optional: if we ran the model K times, how much did the
                  TOP priority id vary? (Jaccard-style)

The ensemble signal is the strongest but also the most expensive. When
`samples <= 1` it is skipped.
"""
from __future__ import annotations
from typing import Iterable


def compute(
    *,
    missing_info_count: int,
    contradiction_flagged: bool,
    priority_confidences: list[float],
    ensemble_top_ids: Iterable[str] | None = None,
) -> tuple[float, dict[str, float]]:
    s_missing = min(0.4, 0.1 * missing_info_count)
    s_contradict = 0.25 if contradiction_flagged else 0.0
    if not priority_confidences:
        s_conf = 0.3
    else:
        avg = sum(priority_confidences) / len(priority_confidences)
        s_conf = (1 - avg) * 0.3
    s_ensemble = 0.0
    if ensemble_top_ids:
        ids = list(ensemble_top_ids)
        if len(ids) > 1:
            most_common = max(set(ids), key=ids.count)
            agreement = ids.count(most_common) / len(ids)
            s_ensemble = (1 - agreement) * 0.35
    total = round(min(0.95, s_missing + s_contradict + s_conf + s_ensemble), 2)
    return total, {"missing": s_missing, "contradict": s_contradict,
                   "confidence": s_conf, "ensemble": s_ensemble}
