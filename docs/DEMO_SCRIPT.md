# Demo script (5 minutes)

Runs fully offline in demo mode (no `ANTHROPIC_API_KEY`). Numbers below are from the seed
(`--seed 42`); the seed is anchored to today's date, so dates move with the calendar but the
story does not.

**Before you start:** `make demo`, open the printed URL, sign in as **Priya Sharma**
(`priya@novapay.example`, password = `SEED_DEMO_PASSWORD`). To start over at any point:
Cmd/Ctrl+K, type "reset", choose **Reset demo data** (re-seeds in a few seconds).

| Time | Beat | What to do | What the audience sees |
|---|---|---|---|
| 0:00 | **Hook** | Land on Command Center. | Health **~73, ↓7 this week**, Dependencies amber (~62). Launch P80 ~8–9 days after target. |
| 0:30 | **Briefing #1** | Read the first card aloud. | "Payments API v2 likely to slip ~4 days; 3 launch epics depend on it. Launch P80 moves from *Mar 8* to *Mar 22*." |
| 1:00 | **Why?** | Click **Why?**; then open **Risk Radar**. | SHAP drivers (reopen after review, time used vs plan, review latency ~2.5x norm, owner at 112%). The critical path (Idempotency keys → Payments API v2 → Mobile checkout UI) is red and animated. Set **Simulate slip** to 9 days: the cascade highlights and P80 moves. |
| 2:00 | **Ask the Twin** | Cmd/Ctrl+J, ask **"What should I do?"** | Streamed agent trace Risk → Planner → Delegation, then three options with forecast deltas (Rebalance ~−22d, Descope ~−10d, Move the date 0d) and 6 actions waiting for approval. |
| 2:45 | **Decide** | Back on Command Center, **See options** → **Choose rebalance**. | Delegation shows Karan Malhotra (Go 5, API design 5, 62% load, growth goal: payments) and Li Wei (Postgres 5, 56% load) with factor bars and one-sentence reasons. **Approve all** (L3): items move, owners are notified, the risk register and forecast refresh. |
| 3:30 | **Communicate** | **Comms Studio** → Executive → **Generate**. | An update in Priya's voice ("Bottom line: …") with RAG badge and citations. Edit one line, **Approve & send**: it posts to the mock #checkout-2-0 channel; the edit becomes a style example. |
| 4:15 | **Trust** | Open an activity item (audit drawer); **Settings → Autonomy**; **Settings → Twin learning**. | Every action with actor (user/twin), before/after and reason; the L1–L4 dial with capped steps; acceptance by type and weight shifts. |
| 4:45 | **Close** | Return to Command Center. | *"TwinPM doesn't just answer questions about your program. It runs it the way you would, and shows its reasoning every time."* |

## If something goes wrong
- Briefing looks stale: Cmd/Ctrl+K → reset, or reload (the hourly worker job also refreshes it).
- Live ticks: with `DEMO_LIVE_TICKS=true` the mock tracker moves a few items every 2 minutes;
  watch the activity feed and the "Live" indicator.
- With a Claude key set, the same flow runs on Claude; answers are worded differently but use
  the same tools, data, policy gate and citations.
