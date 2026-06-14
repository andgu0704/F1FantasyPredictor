"""Walk-forward backtest of the predictors.

For every test round we train/derive each predictor only from earlier rounds and
score how well its predicted driver ranking matches the actual race result,
using Spearman rank correlation within the round (and top-5 hit rate). This is
done in "goodness" units (position-based) because we only hold the current
fantasy-price snapshot, not historical ones — but the question a backtest must
answer ("does this predictor rank who performs well better than the baseline?")
is exactly what this measures.

    uv run python -m f1fantasy.backtest
"""

from __future__ import annotations

import numpy as np

from f1fantasy.db import connect
from f1fantasy.features import Row, build_rows
from f1fantasy.ml_model import RidgeModel

# Heuristic factor clamps, mirroring predictor/heuristic.py but in goodness space.
FORM_CLAMP = (0.80, 1.20)
TRACK_CLAMP = (0.85, 1.15)
MIN_TRAIN_ROWS = 100
TOP_N = 5


def _clamp(x, lo, hi):
    return max(lo, min(hi, x))


def _spearman(pred: list[float], actual: list[float]) -> float | None:
    if len(pred) < 3:
        return None
    pr = np.argsort(np.argsort(pred))
    ar = np.argsort(np.argsort(actual))
    if pr.std() == 0 or ar.std() == 0:
        return None
    return float(np.corrcoef(pr, ar)[0, 1])


def _heuristic_pred(f: list[float]) -> float:
    recent_form, season_form, reliability, track_history = f[0], f[1], f[2], f[3]
    if season_form <= 0:
        return recent_form
    form = _clamp(recent_form / season_form, *FORM_CLAMP)
    track = _clamp(track_history / season_form, *TRACK_CLAMP)
    return season_form * form * track * reliability


def _naive_pred(f: list[float]) -> float:
    return f[1]  # season_form (season-to-date average)


def backtest(alpha: float = 1.0) -> dict:
    rows = build_rows(connect())
    groups: dict[tuple[int, int], list[Row]] = {}
    for r in rows:
        groups.setdefault((r.season, r.round), []).append(r)
    keys = sorted(groups)  # (season, round) sorts chronologically

    methods = ("naive", "heuristic", "ml")
    sp = {m: [] for m in methods}
    hit = {m: [] for m in methods}
    n_rounds = 0

    for i, key in enumerate(keys):
        train = [r for k in keys[:i] for r in groups[k]]
        if len(train) < MIN_TRAIN_ROWS:
            continue
        test = groups[key]
        actual = [r.label for r in test]

        model = RidgeModel(alpha).fit(
            np.array([r.features for r in train]), np.array([r.label for r in train])
        )
        preds = {
            "naive": [_naive_pred(r.features) for r in test],
            "heuristic": [_heuristic_pred(r.features) for r in test],
            "ml": list(model.predict(np.array([r.features for r in test]))),
        }

        actual_top = {idx for idx in np.argsort(actual)[::-1][:TOP_N]}
        for m in methods:
            s = _spearman(preds[m], actual)
            if s is not None:
                sp[m].append(s)
            pred_top = {idx for idx in np.argsort(preds[m])[::-1][:TOP_N]}
            hit[m].append(len(pred_top & actual_top) / TOP_N)
        n_rounds += 1

    return {
        "test_rounds": n_rounds,
        "spearman": {m: float(np.mean(sp[m])) for m in methods},
        "top5_hit_rate": {m: float(np.mean(hit[m])) for m in methods},
    }


if __name__ == "__main__":
    res = backtest()
    print(f"Walk-forward backtest over {res['test_rounds']} rounds\n")
    print(f"{'method':12}{'Spearman ρ':>12}{'top-5 hit':>12}")
    for m in ("naive", "heuristic", "ml"):
        print(f"{m:12}{res['spearman'][m]:>12.3f}{res['top5_hit_rate'][m]:>12.1%}")
