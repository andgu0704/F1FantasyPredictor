"""Feature engineering: causality + shape, against the live DB."""

from __future__ import annotations

import pytest

from f1fantasy.db import connect
from f1fantasy.features import FEATURE_NAMES, build_rows, goodness


@pytest.fixture(scope="module")
def rows():
    rs = build_rows(connect())
    if not rs:
        pytest.skip("database not populated — run the ingestion first")
    return rs


def test_goodness_monotonic():
    assert goodness(1) > goodness(5) > goodness(20) >= 0
    assert goodness(None) == 0.0  # DNF


def test_feature_vector_matches_names(rows):
    assert all(len(r.features) == len(FEATURE_NAMES) for r in rows)


def test_no_round_one_rows(rows):
    # Round 1 has no prior-race history, so it cannot produce causal features.
    assert all(r.round >= 2 for r in rows)


def test_features_finite(rows):
    import math
    assert all(math.isfinite(x) for r in rows for x in r.features)
