# ML subsystem

All models are pure functions of `ProgramData` (one DataFrame per table), built from the
database (`load_program_data`) or straight from the seed (`from_dataset`), so every model is
unit tested without a database. Persistence lives in `services/ml_jobs.py`.

`make train` trains every model into the registry and refreshes all outputs
(predictions, forecasts, anomalies, themes, health, model-sourced risks). The worker retrains
nightly and refreshes hourly.

## Registry

`models/{name}/{version}/model.joblib` + `metadata.json` (purpose, algorithm, features,
metrics, split, training data hash, timestamp). `models/{name}/LATEST` points at the serving
version. Models are currently global (trained on the demo tenant); per-tenant models are a
roadmap item.

Numbers below are from `make train` on the seed (`--seed 42`, run 2026-11-22).

## 7.1 Delay risk classifier (`ml/delay.py`, `ml/features.py`)

- **Target:** the item finishes after its due date.
- **Training rows:** in-flight snapshots at 30%, 55% and 80% of each item's planned
  start-to-due window, with every feature computed *as of the snapshot* from events at or
  before it (no leakage). Labels are known for finished items and for open items already
  past due; open items not yet due are censored and excluded.
- **Features:** age, days in current status, status, type, story points, reopen count, PR
  review hours and ratio to the team norm, team review latency ratio, blockers encountered or
  open, upstream dependency risk, owner utilisation (sprint points plus carry-over / sprint
  capacity), owner on-time rate (90 days), team velocity trend (last 2 sprints / 6-sprint
  mean), comments, days to due, share of planned time used.
- **Model:** XGBoost (600 trees, depth 3, lr 0.02), time-based split 65% fit / 15% isotonic
  calibration / 20% validation; refit on fit+calibration for serving. Scores are clipped to
  [0.02, 0.97].
- **Explain:** SHAP TreeExplainer; top 3 positive contributions with labels such as
  "PR review time 2.6x the team norm" or "Owner at 112% utilisation".
- **Serving rules:** started items past their due date are certain to finish late (0.97,
  drivers still shown). Unstarted items get the team's 90-day late rate, scaled by upstream
  dependency risk, because the model's causes are not observable before work starts.
- **Metrics (validation):** ROC-AUC 0.83, precision@10 0.90, Brier 0.21.
- **Limitations:** on other seeds AUC varies (seed 7: ~0.69); the storyline sprints shift the
  distribution in the validation window. Synthetic data, so absolute numbers are optimistic.

## 7.2 Effort estimator (`ml/effort.py`)

Gradient-boosted quantile regression (q = 0.1 / 0.5 / 0.9) on type, points, team, labels and a
16-dim PCA of the text embedding. The 10–90 band is widened by a conformal factor fitted on the
validation slice so it covers ~80%. Returns the 3 most similar finished items (cosine on
embeddings). **Metrics:** MAE 2.5 days, interval coverage 0.80 (scale 3.3).

## 7.3 Delivery forecaster (`ml/forecast.py`, `ml/scenario.py`, `ml/backtest.py`)

Vectorised Monte Carlo (10,000 simulations, ~0.25 s). Remaining milestone items are grouped
into packets by (team, epic, gate); gated packets start when the epic they depend on is done.
Per-team throughput is bootstrapped from the last 6 completed sprints and scaled by the
program allocation (`domain.PROGRAM_ALLOCATION` = 0.53, the share of team time on the launch)
and any capacity change. Each item adds 50–100% overrun with probability equal to its delay
risk. Output: P50/P80/P95, histogram, per-epic P80, on-time probability and assumptions.

The what-if simulator applies `add_scope`, `remove_scope`, `capacity_change`, `reassign`
(re-scores moved items with the delay model for the new owner) and `date_shift`, and re-runs
with the same random seed (common random numbers) so deltas reflect the change.

On the seed: launch P80 is 9 days after target, it moved 15 days over the last two weeks, the
Payments slip accounts for ~30 days versus a no-slip counterfactual, and the rebalance plan
recovers ~73% of that.

**Backtest** (`python -m twinpm.ml.backtest`): every finished epic forecast from cut-offs at
25/50/75% of its life. Result: P80 hit-rate 0.11, mean error +38 days. The forecaster assumes
fixed scope; background epics kept receiving new items after each cut-off, so it is
systematically early on them. A scope-growth model is on the roadmap. The launch forecast is
less exposed because its backlog is mostly defined, but treat its P80 as optimistic.

## 7.4 Anomaly detection (`ml/anomaly.py`)

Per team and metric, a z-score against a 28-day baseline lagged 14 days (|z| > 2.5), plus an
Isolation Forest (contamination 3%) on the standardised daily metric vector. Results are
merged, deduplicated to the latest finding per metric over the last 21 days, and explained in
words. On the seed it flags Payments velocity (z −2.7) and review latency (z +3.2).

## 7.5 Themes and opportunity scoring (`ml/themes.py`)

Feedback is embedded with `all-MiniLM-L6-v2` and clustered with HDBSCAN. When HDBSCAN finds
fewer than 3 clusters or labels over 35% as noise, KMeans runs with k chosen by silhouette
(4–7). Labels come from class-based TF-IDF keywords (the LLM can relabel them when a key is
set). On the seed KMeans picks k = 6 (adjusted Rand index 0.93 against the true themes).
Opportunity = 100 × (0.30 volume + 0.20 recency-weighted growth + 0.20 sentiment severity +
0.15 segment value + 0.15 strategic fit with objectives), with the breakdown stored.
Bulk export ranks first (38 items, sentiment −0.55).

## 7.6 Delegation ranker (`ml/delegation.py`)

score = 0.35 skill match + 0.25 availability + 0.15 throughput on similar work + 0.10 growth
alignment + 0.15 context continuity − 0.5 over-allocation − 0.2 PTO overlap. Required skills
come from keyword rules over labels, title and epic. The rebalance planner moves critical-path
and overloaded-owner work to people under 85% utilisation with skill match ≥ 0.4. It never
moves critical work within the bottleneck team and never pushes other work into it.
**Fairness:** inputs are work signals only; a test asserts no protected attribute (name,
gender, age, nationality, timezone, ...) is a feature or is read by the ranker.

## 7.7 Preference model (`ml/preference.py`)

Each suggestion response is logged with context features. A Beta(3,2)-smoothed acceptance prior
by type covers cold start; after 8 events a per-user logistic re-ranker blends in, weighted
by event count. Delegation weights shift toward factors that separate accepted from rejected
reassignments, bounded to ±30% of the defaults. Edits to status reports add style examples to
the persona (most recent 10).

## 7.8 Program health (`ml/health.py`)

health = 0.30 schedule + 0.20 scope + 0.20 quality + 0.15 dependencies + 0.15 team (weights
per program). Schedule: 100 when P80 ≤ target, falling linearly to 0 at 30 days late. Scope:
scope growth over 2 sprints. Quality: bug inflow and reopen rate against a 90-day baseline.
Dependencies: open upstream blockers on launch scope and their mean delay risk. Team:
utilisation spread, people above 85% and team sentiment. On the seed: 73 (schedule 70,
dependencies 60).
