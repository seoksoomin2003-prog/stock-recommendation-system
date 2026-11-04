"""Data-quality confidence independent from score magnitude."""

from typing import Iterable
from contracts.normalized_data import DataStatus, NormalizedData


def calculate_confidence(items: Iterable[NormalizedData]) -> float:
    values = list(items)
    if not values:
        return 0.0
    weights = {DataStatus.REAL: 1.0, DataStatus.REAL_CURRENT: 1.0, DataStatus.CACHED: 0.9, DataStatus.STALE: 0.5,
               DataStatus.FALLBACK: 0.2, DataStatus.UNAVAILABLE: 0.0, DataStatus.ERROR: 0.0}
    return round(sum(weights[x.status] * x.confidence for x in values) / len(values), 4)
