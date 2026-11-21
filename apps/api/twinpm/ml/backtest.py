"""Forecaster backtest: replay history at past cut-offs and measure the P80 hit-rate.

For every epic that finished in the data, forecast its completion from cut-offs at 25%, 50%
and 75% of its lifetime, using only data visible at the cut-off (`as_of`), and check whether
the actual completion landed on or before the P80 date.

`python -m twinpm.ml.backtest`
"""

from __future__ import annotations

from typing import Any

import pandas as pd

from twinpm.domain import PROGRAM_ALLOCATION
from twinpm.ml import delay
from twinpm.ml.data import ProgramData, as_of
from twinpm.ml.forecast import build_input, simulate


def run(data: ProgramData, model: delay.DelayModel, sims: int = 2000) -> dict[str, Any]:
    it = data.items
    results = []
    for epic_id, g in it.groupby("epic_id"):
        if g["done_at"].isna().any() or g["started_at"].isna().all() or len(g) < 5:
            continue
        start, end = g["started_at"].min(), g["done_at"].max()
        for frac in (0.25, 0.5, 0.75):
            t = start + (end - start) * frac
            past = as_of(data, t.to_pydatetime())
            risks = {r.work_item_id: r.score for r in delay.score_open_items(past, model)}
            inp = build_input(past, None, risks, scope={epic_id})
            if inp.items.empty:
                continue
            # The epic only gets the share of its team's throughput it received recently.
            team = g["team_id"].iloc[0]
            lo = pd.Timestamp(t) - pd.Timedelta(days=42)
            done = past.items[(past.items["team_id"] == team) & (past.items["done_at"] > lo)]
            share = float(
                done.loc[done["epic_id"] == epic_id, "story_points"].sum()
                / max(done["story_points"].sum(), 1.0)
            )
            inp.capacity_factor[team] = max(share, 0.05) / PROGRAM_ALLOCATION
            res = simulate(inp, sims)
            hit = end.date() <= res.p80
            results.append(
                {
                    "epic_id": str(epic_id),
                    "cutoff": t.date().isoformat(),
                    "fraction": frac,
                    "p80": res.p80.isoformat(),
                    "actual": end.date().isoformat(),
                    "hit": bool(hit),
                    "error_days": (end.date() - res.p80).days,
                }
            )
    df = pd.DataFrame(results)
    return {
        "cases": len(df),
        "p80_hit_rate": round(float(df["hit"].mean()), 3) if len(df) else None,
        "mean_error_days": round(float(df["error_days"].mean()), 1) if len(df) else None,
        "results": results,
        "note": "Delay risks at each cut-off come from the current model (trained on all "
        "history), so the hit-rate is mildly optimistic.",
    }


if __name__ == "__main__":
    import asyncio
    import json

    from twinpm.ml.registry import ModelRegistry
    from twinpm.services.ml_jobs import load_demo_data

    async def _main() -> None:
        data = await load_demo_data()
        loaded = ModelRegistry.default().load(delay.NAME)
        model = loaded[0] if loaded else delay.train(data)[0]
        out = run(data, model)
        print(json.dumps({k: v for k, v in out.items() if k != "results"}, indent=2))

    asyncio.run(_main())
