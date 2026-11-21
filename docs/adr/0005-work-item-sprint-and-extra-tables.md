# ADR 0005: Schema additions beyond Section 4

Status: accepted

- `work_items.sprint_id`: utilisation is defined as (points committed to the current sprint
  plus open carry-over from earlier sprints) / sprint capacity. That needs the sprint link.
- `refresh_tokens`, `api_tokens`: refresh-token rotation with reuse detection, and per-user
  tokens for the MCP server.
- `time_off`: PTO for sprint-plan capacity and the delegation PTO-overlap penalty.
- `health_snapshots`: the daily health trend line.
- Utilisation, story-point capacity (8 points per 40-hour sprint) and the program allocation
  factor live in `twinpm/domain.py` so the seed generator, features and services agree.
