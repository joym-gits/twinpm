"""Deterministic synthetic data generator for the NovaPay / Checkout 2.0 demo.

Pure function of (seed, anchor date): `generate(seed, anchor)` returns plain row dicts per
table, so two runs with the same inputs are byte-for-byte identical (see `Dataset.digest`).

Work-item durations come from a causal model, so the ML models learn real signal:

    base_days  ~ lognormal(type, points)
    duration   = base_days * noise
                 * (1 + 1.6 * max(0, utilisation - 0.85))   # owner overload
                 * (1 + 0.28 * blockers)                    # dependency waits
                 * (1 + 0.045 * max(0, review_hours - 8))   # slow code review
                 * (1 + 0.30 * reopens)                     # rework

An item is late when `done_at > due_date`; due dates are set from the un-inflated estimate.
"""

from __future__ import annotations

import hashlib
import json
import uuid
from dataclasses import dataclass, field
from datetime import UTC, date, datetime, time, timedelta
from typing import Any

import numpy as np

from twinpm.domain import SPRINT_DAYS, capacity_points
from twinpm.seed import roster
from twinpm.seed.plan import (
    EPIC_DEPENDENCIES,
    EPICS,
    INITIATIVES,
    LAUNCH_EPICS,
    LAUNCH_NAME,
    LAUNCH_WEEKS_OUT,
    OBJECTIVES,
    PROGRAM_NAME,
    PROGRAM_OBJECTIVE,
    EpicSpec,
)

NAMESPACE = uuid.UUID("6f1c3a52-6d1b-4f0e-9a51-1c0b7f7f2a10")
N_PAST_SPRINTS = 13
STORY_SPRINTS = {11, 12, 13}  # last two completed sprints + the current one
TYPE_BASE_DAYS = {"story": 1.0, "task": 0.8, "bug": 0.7, "spike": 0.9}
POINTS = [1, 2, 3, 5, 8]
POINT_P = [0.10, 0.20, 0.30, 0.25, 0.15]
TYPES = ["story", "task", "bug", "spike"]
TYPE_P = [0.50, 0.25, 0.20, 0.05]
CALENDAR_FACTOR = 1.4  # working days to calendar days
STORY_LOAD = {"vikram": 1.22, "karan": 0.70, "liwei": 0.64}
# Payments loses focus to incidents and review load during the storyline sprints.
STORY_FOCUS_PENALTY = 2.2
TITLES = {
    "pay_api": [
        "Implement {} endpoint",
        "Validate {} request schema",
        "Add {} error codes",
        "Harden {} auth scopes",
        "Write contract tests for {}",
    ],
    "idem": ["Store idempotency key for {}", "Replay protection for {}", "Expire keys for {}"],
    "mob_ui": [
        "Build {} screen",
        "Wire {} to Payments API v2",
        "Animate {} transitions",
        "Accessibility pass on {}",
    ],
    "ios_wallet": ["Apple Pay sheet for {}", "iOS {} token handling"],
    "android_wallet": ["Google Pay flow for {}", "Android {} token handling"],
    "rate_limit": ["Token bucket for {}", "Rate limit headers on {}", "Redis cluster for {}"],
    "fraud": ["Fraud score hook on {}", "Kafka consumer for {} signals", "Fraud rules for {}"],
    "obs": ["Trace {} spans", "SLO dashboard for {}", "Alert on {} latency"],
    "ledger": ["Migrate {} ledger entries", "Backfill {} balances", "Reconcile {} journal"],
    "refunds": ["Refund status for {}", "Webhook for {} refunds"],
    "saved_cards": ["Vault {} cards", "PCI scope review for {}"],
    "kafka": ["Kafka topic for {}", "Schema registry for {}", "Consumer lag alert for {}"],
    "retention": ["Retention job for {}", "Purge {} after policy window"],
    "bulk_export": ["CSV export for {}", "Async export job for {}"],
    "mob_ds": ["Design token for {}", "Component {} in design system"],
    "dark_mode": ["Dark palette for {}", "Theme switch on {}"],
    "upi": ["UPI mandate for {}", "Autopay retry for {}"],
    "fx": ["FX rate cache for {}", "Currency display for {}"],
}
NOUNS = [
    "payments",
    "refunds",
    "captures",
    "authorisations",
    "payouts",
    "checkout",
    "cart",
    "wallets",
    "cards",
    "merchants",
    "settlements",
    "disputes",
    "webhooks",
    "sessions",
    "tokens",
    "invoices",
    "orders",
    "customers",
]


@dataclass
class Dataset:
    seed: int
    anchor: date
    tables: dict[str, list[dict[str, Any]]] = field(default_factory=dict)

    def add(self, table: str, row: dict[str, Any]) -> dict[str, Any]:
        self.tables.setdefault(table, []).append(row)
        return row

    def digest(self) -> str:
        blob = json.dumps(self.tables, sort_keys=True, default=str).encode()
        return hashlib.sha256(blob).hexdigest()

    def counts(self) -> dict[str, int]:
        return {k: len(v) for k, v in sorted(self.tables.items())}


@dataclass
class _Item:
    row: dict[str, Any]
    epic: EpicSpec
    team: str
    person: str | None
    sprint: int | None
    load: float
    review_hours: float
    blockers: int
    reopens: int
    duration: float
    planned: float


class Generator:
    def __init__(self, seed: int, anchor: date) -> None:
        self.seed = seed
        self.anchor = anchor
        self.rng = np.random.default_rng(seed)
        self.now = datetime.combine(anchor, time(9, 0), UTC)
        self.ds = Dataset(seed, anchor)
        self.org_id = self.uid("org")
        self.ids: dict[str, uuid.UUID] = {}
        self.cur_start = anchor - timedelta(days=6)
        self.sprint_starts = [
            self.cur_start - timedelta(days=SPRINT_DAYS * (N_PAST_SPRINTS - i))
            for i in range(N_PAST_SPRINTS + 1)
        ]
        self.items: list[_Item] = []
        self.counters: dict[str, int] = {}

    # ---------------------------------------------------------------- helpers
    def uid(self, *parts: object) -> uuid.UUID:
        return uuid.uuid5(NAMESPACE, ":".join(str(p) for p in (self.seed, *parts)))

    def at(self, days: float) -> datetime:
        """Anchor-relative timestamp, rounded to the minute."""
        return (self.now + timedelta(days=float(days))).replace(second=0, microsecond=0)

    def stamp(self, row: dict[str, Any], created: datetime | None = None) -> dict[str, Any]:
        ts = created or self.at(-200)
        row.setdefault("created_at", ts)
        row.setdefault("updated_at", ts)
        row.setdefault("org_id", self.org_id)
        return row

    def u(self, lo: float, hi: float) -> float:
        return float(self.rng.uniform(lo, hi))

    # ---------------------------------------------------------------- build
    def build(self) -> Dataset:
        self._org_and_people()
        self._program()
        self._work()
        self._dependencies()
        self._events_and_metrics()
        self._signals()
        self._risks()
        self._health_history()
        self._persona_and_policies()
        self._integrations()
        return self.ds

    def _org_and_people(self) -> None:
        ds = self.ds
        ds.add(
            "organizations",
            {
                "id": self.org_id,
                "name": roster.ORG_NAME,
                "slug": roster.ORG_SLUG,
                "plan": "enterprise",
                "settings": {"data_retention_days": 730, "min_group_size": 5, "demo": True},
                "created_at": self.at(-200),
                "updated_at": self.at(-200),
            },
        )
        for team in roster.TEAMS:
            tid = self.ids[f"team:{team.key}"] = self.uid("team", team.key)
            ds.add(
                "teams",
                self.stamp(
                    {
                        "id": tid,
                        "name": team.name,
                        "description": team.description,
                        "manager_person_id": None,
                        "deleted_at": None,
                    }
                ),
            )
        skills = sorted({s for p in roster.PEOPLE for s in p.skills})
        for s in skills:
            self.ids[f"skill:{s}"] = self.uid("skill", s)
            ds.add(
                "skills",
                self.stamp(
                    {
                        "id": self.ids[f"skill:{s}"],
                        "name": s,
                        "category": roster.SKILL_CATEGORIES.get(s, "other"),
                    }
                ),
            )
        admin_key, admin_name, admin_role = roster.ADMIN
        users = [(admin_key, admin_name, admin_role)] + [
            (p.key, p.name, p.role) for p in roster.PEOPLE if p.role
        ]
        for key, name, role in users:
            self.ids[f"user:{key}"] = self.uid("user", key)
            ds.add(
                "users",
                self.stamp(
                    {
                        "id": self.ids[f"user:{key}"],
                        "email": roster.email_for(key),
                        "name": name,
                        "password_hash": "",
                        "role": role,
                        "is_active": True,
                        "last_login_at": None,
                        "timezone": "Asia/Kolkata",
                        "deleted_at": None,
                    }
                ),
            )
        for p in roster.PEOPLE:
            pid = self.ids[f"person:{p.key}"] = self.uid("person", p.key)
            ds.add(
                "people",
                self.stamp(
                    {
                        "id": pid,
                        "name": p.name,
                        "title": p.title,
                        "team_id": self.ids[f"team:{p.team}"] if p.team else None,
                        "capacity_hours_per_week": p.capacity,
                        "timezone": p.timezone,
                        "growth_goals": list(p.growth_goals),
                        "avatar_url": None,
                        "user_id": self.ids.get(f"user:{p.key}"),
                        "deleted_at": None,
                    }
                ),
            )
            for skill, level in p.skills.items():
                ds.add(
                    "person_skills",
                    self.stamp(
                        {
                            "id": self.uid("ps", p.key, skill),
                            "person_id": pid,
                            "skill_id": self.ids[f"skill:{skill}"],
                            "level": level,
                            "evidence_count": int(level * 3 + self.rng.integers(0, 5)),
                        }
                    ),
                )
        for team in roster.TEAMS:
            row = next(r for r in ds.tables["teams"] if r["id"] == self.ids[f"team:{team.key}"])
            row["manager_person_id"] = self.ids[f"person:{team.manager}"]
        # Upcoming PTO, used by sprint planning and the delegation PTO penalty.
        for key, start, length in (("meera", 9, 5), ("emily", 20, 4), ("marcus", 3, 2)):
            ds.add(
                "time_off",
                self.stamp(
                    {
                        "id": self.uid("pto", key),
                        "person_id": self.ids[f"person:{key}"],
                        "start_date": self.anchor + timedelta(days=start),
                        "end_date": self.anchor + timedelta(days=start + length - 1),
                        "kind": "pto",
                    }
                ),
            )

    def _program(self) -> None:
        ds = self.ds
        pid = self.ids["program"] = self.uid("program", "checkout2")
        self.target = self.anchor + timedelta(weeks=LAUNCH_WEEKS_OUT)
        ds.add(
            "programs",
            self.stamp(
                {
                    "id": pid,
                    "name": PROGRAM_NAME,
                    "objective": PROGRAM_OBJECTIVE,
                    "status": "active",
                    "target_date": self.target,
                    "owner_user_id": self.ids["user:priya"],
                    "health_weights": {
                        "schedule": 0.30,
                        "scope": 0.20,
                        "quality": 0.20,
                        "dependencies": 0.15,
                        "team": 0.15,
                    },
                    "deleted_at": None,
                }
            ),
        )
        q = f"{self.anchor.year}-Q{(self.anchor.month - 1) // 3 + 1}"
        for o in OBJECTIVES:
            self.ids[f"objective:{o.key}"] = self.uid("objective", o.key)
            ds.add(
                "objectives",
                self.stamp(
                    {
                        "id": self.ids[f"objective:{o.key}"],
                        "program_id": pid,
                        "title": o.title,
                        "key_results": [
                            {"title": kr, "progress": round(self.u(0.1, 0.6), 2)}
                            for kr in o.key_results
                        ],
                        "quarter": q,
                    }
                ),
            )
        for i in INITIATIVES:
            self.ids[f"initiative:{i.key}"] = self.uid("initiative", i.key)
            score = round(i.reach * i.impact * i.confidence / i.effort, 1)
            bv, tc, rr, size = i.wsjf
            ds.add(
                "initiatives",
                self.stamp(
                    {
                        "id": self.ids[f"initiative:{i.key}"],
                        "program_id": pid,
                        "objective_id": self.ids[f"objective:{i.objective}"],
                        "title": i.title,
                        "description": i.description,
                        "roadmap_bucket": i.bucket,
                        "rice": {
                            "reach": i.reach,
                            "impact": i.impact,
                            "confidence": i.confidence,
                            "effort": i.effort,
                            "score": score,
                        },
                        "wsjf": {
                            "business_value": bv,
                            "time_criticality": tc,
                            "risk_reduction": rr,
                            "job_size": size,
                            "score": round((bv + tc + rr) / size, 2),
                        },
                        "target_date": self.target if i.bucket == "now" else None,
                        "status": {"now": "in_progress", "next": "planned", "later": "proposed"}[
                            i.bucket
                        ],
                        "deleted_at": None,
                    }
                ),
            )
        team_prefix = {t.key: t.prefix for t in roster.TEAMS}
        for n, e in enumerate(EPICS, start=1):
            self.ids[f"epic:{e.key}"] = self.uid("epic", e.key)
            ds.add(
                "epics",
                self.stamp(
                    {
                        "id": self.ids[f"epic:{e.key}"],
                        "initiative_id": self.ids[f"initiative:{e.initiative}"],
                        "team_id": self.ids[f"team:{e.team}"],
                        "key": f"{team_prefix[e.team]}-E{n}",
                        "title": e.title,
                        "description": f"{e.title} for {PROGRAM_NAME}.",
                        "status": e.status,
                        "target_date": self.target - timedelta(days=21) if e.launch else None,
                        "deleted_at": None,
                    }
                ),
            )
        self.ids["milestone"] = self.uid("milestone", "launch")
        ds.add(
            "milestones",
            self.stamp(
                {
                    "id": self.ids["milestone"],
                    "program_id": pid,
                    "name": LAUNCH_NAME,
                    "target_date": self.target,
                    "scope": [str(self.ids[f"epic:{k}"]) for k in LAUNCH_EPICS],
                    "latest_forecast": {},
                }
            ),
        )
        for n_sprint, s in enumerate(self.sprint_starts):
            for team in roster.TEAMS:
                ds.add(
                    "sprints",
                    self.stamp(
                        {
                            "id": self.uid("sprint", team.key, n_sprint),
                            "team_id": self.ids[f"team:{team.key}"],
                            "name": f"{team.name} Sprint {n_sprint + 1}",
                            "start_date": s,
                            "end_date": s + timedelta(days=SPRINT_DAYS - 1),
                            "goal": "",
                            "committed_points": 0.0,
                            "completed_points": 0.0,
                        },
                        created=self.at((s - self.anchor).days - 3),
                    ),
                )

    # ---------------------------------------------------------------- work items
    def _epic_weights(self, team: str, sprint: int) -> tuple[list[EpicSpec], np.ndarray]:
        epics = [e for e in EPICS if e.team == team]
        mix = min(1.0, max(0.0, (sprint - 8) / 3))
        w = np.array([(1 - mix) * e.weight_history + mix * e.weight_recent for e in epics])
        w = np.clip(w, 0, None)
        return epics, w / w.sum()

    def _key(self, team: str) -> str:
        prefix = next(t.prefix for t in roster.TEAMS if t.key == team)
        self.counters[prefix] = self.counters.get(prefix, 100) + 1
        return f"{prefix}-{self.counters[prefix]}"

    def _title(self, epic: EpicSpec) -> str:
        tpl = TITLES[epic.key][int(self.rng.integers(0, len(TITLES[epic.key])))]
        return tpl.format(NOUNS[int(self.rng.integers(0, len(NOUNS)))])

    def _new_item(
        self,
        epic: EpicSpec,
        team: str,
        person: str | None,
        sprint: int | None,
        start_offset: float | None,
        created_offset: float,
        forced_reopen: bool = False,
        max_points: float = 8,
    ) -> _Item:
        """Create an item's intrinsic attributes. Duration is set later by `_finalize`."""
        rng = self.rng
        pts = 3 if forced_reopen else int(rng.choice(POINTS, p=POINT_P))
        if pts > max_points:  # fit the remaining sprint capacity
            pts = max([p for p in POINTS if p <= max_points] or [1])
        typ = str(rng.choice(TYPES, p=TYPE_P))
        team_spec = next(t for t in roster.TEAMS if t.key == team)
        review_mult = 2.5 if team == "payments" and sprint in STORY_SPRINTS else 1.0
        review = float(team_spec.base_review_hours * review_mult * rng.lognormal(0, 0.35))
        depends = any(b for b, d in EPIC_DEPENDENCIES if d == epic.key)
        p_block = 0.35 if depends and epic.launch else 0.08
        blockers = int(rng.random() < p_block) + int(rng.random() < p_block * 0.3)
        p_reopen = 0.08 + 0.10 * (typ == "bug") + 0.04 * (pts >= 5)
        if team == "payments" and sprint in STORY_SPRINTS:
            p_reopen += 0.12
        reopens = int(rng.random() < p_reopen) + int(rng.random() < p_reopen * 0.25)
        if forced_reopen:
            reopens = max(reopens, 1)
        base = TYPE_BASE_DAYS[typ] * (1 + 0.55 * pts) * CALENDAR_FACTOR
        planned = base * self.u(1.12, 1.28)
        created = self.at(created_offset)
        started = self.at(start_offset) if start_offset is not None else None
        wid = self.uid("wi", len(self.items))
        row = self.stamp(
            {
                "id": wid,
                "epic_id": self.ids[f"epic:{epic.key}"],
                "team_id": self.ids[f"team:{team}"],
                "sprint_id": self.uid("sprint", team, sprint) if sprint is not None else None,
                "key": self._key(team),
                "title": self._title(epic),
                "description": "",
                "type": typ,
                "status": "todo",
                "story_points": float(pts),
                "estimate_days": round(planned / CALENDAR_FACTOR, 1),
                "assignee_person_id": self.ids[f"person:{person}"] if person else None,
                "created_at_src": created,
                "started_at": started,
                "done_at": None,
                "due_date": (started + timedelta(days=planned)).date()
                if started
                else (self.target - timedelta(days=int(self.rng.integers(25, 45)))),
                "reopen_count": 0,
                "pr_review_hours": 0.0,
                "comments_count": 0,
                "labels": list(epic.labels),
                "external_ref": {},
                "deleted_at": None,
            },
            created=created,
        )
        row["description"] = (
            f"{row['title']}. Part of {epic.title}. Acceptance: covered by automated tests, "
            "reviewed, and deployed behind a feature flag."
        )
        row["external_ref"] = {"provider": "jira", "key": row["key"]}
        noise = float(rng.lognormal(0, 0.12))
        item = _Item(
            row, epic, team, person, sprint, 0.0, review, blockers, reopens, base * noise, planned
        )
        self.items.append(item)
        return item

    def _finalize(self, it: _Item, load: float) -> None:
        """Apply the causal inflation model given the owner's true utilisation."""
        it.load = load
        it.duration *= (
            (1 + 1.6 * max(0.0, load - 0.85))
            * (1 + 0.28 * it.blockers)
            * (1 + 0.045 * max(0.0, it.review_hours - 8))
            * (1 + 0.30 * it.reopens)
        )
        if it.team == "payments" and it.sprint in STORY_SPRINTS:
            it.duration *= STORY_FOCUS_PENALTY
        start = it.row["started_at"]
        if start is not None:
            done = start + timedelta(days=it.duration)
            it.row["done_at"] = done.replace(second=0, microsecond=0) if done <= self.now else None

    def _carry_points(self, person: str, sprint_start: datetime) -> float:
        return float(
            sum(
                it.row["story_points"]
                for it in self.items
                if it.person == person
                and it.sprint is not None
                and it.row["started_at"] is not None
                and it.row["started_at"] < sprint_start
                and (it.row["done_at"] is None or it.row["done_at"] > sprint_start)
            )
        )

    def _work(self) -> None:
        for sprint, s in enumerate(self.sprint_starts):
            s_off = (s - self.anchor).days
            s_dt = datetime.combine(s, time(0), UTC)
            for team in roster.TEAMS:
                epics, weights = self._epic_weights(team.key, sprint)
                for m in roster.team_members(team.key):
                    load = self.u(0.72, 0.92)
                    if sprint in STORY_SPRINTS:
                        if team.key == "payments":
                            load = STORY_LOAD.get(m.key, load + 0.05)
                        elif m.key in STORY_LOAD:
                            load = STORY_LOAD[m.key]
                    cap = capacity_points(m.capacity)
                    carry = self._carry_points(m.key, s_dt)
                    # Planning nets out carry-over, so utilisation tracks the intended load.
                    target = max(load * cap - carry, 1.0)
                    if m.key == "vikram" and sprint == 13:
                        target = max(target, 6.0)  # room for the two reopened storyline items
                    new: list[_Item] = []
                    total, forced = 0.0, 0
                    while target - total >= 1:
                        epic = epics[int(self.rng.choice(len(epics), p=weights))]
                        if m.key == "vikram" and sprint in STORY_SPRINTS:
                            epic = next(e for e in EPICS if e.key == "pay_api")
                        force = m.key == "vikram" and sprint == 13 and forced < 2
                        start = s_off + (0.1 if force else self.u(0, 5))
                        item = self._new_item(
                            epic,
                            team.key,
                            m.key,
                            sprint,
                            start if start <= 0 else None,
                            s_off - self.u(1, 21),
                            forced_reopen=force,
                            max_points=target - total,
                        )
                        new.append(item)
                        forced += int(force)
                        total += item.row["story_points"]
                    util = (total + carry) / cap
                    for item in new:
                        self._finalize(item, util)
        # Unstarted backlog for each epic.
        for e in EPICS:
            members = roster.team_members(e.team)
            for n in range(e.backlog_items):
                person = members[n % len(members)].key if n % 3 else None
                self._finalize(self._new_item(e, e.team, person, None, None, -self.u(20, 80)), 0.8)

    # ---------------------------------------------------------------- dependencies
    def _dependencies(self) -> None:
        ds = self.ds
        for blocker, blocked in EPIC_DEPENDENCIES:
            b_team = next(e.team for e in EPICS if e.key == blocker)
            ds.add(
                "dependencies",
                self.stamp(
                    {
                        "id": self.uid("dep", blocker, blocked),
                        "from_type": "epic",
                        "from_id": self.ids[f"epic:{blocker}"],
                        "to_type": "epic",
                        "to_id": self.ids[f"epic:{blocked}"],
                        "kind": "blocks",
                        "owning_team_id": self.ids[f"team:{b_team}"],
                        "status": "resolved" if blocker in ("kafka",) else "open",
                    }
                ),
            )
        open_api = [i for i in self.items if i.epic.key == "pay_api" and i.row["done_at"] is None]
        dependents = [
            i
            for i in self.items
            if i.epic.key in ("mob_ui", "rate_limit", "fraud", "ios_wallet", "android_wallet")
            and i.row["done_at"] is None
        ]
        n_edges = 0
        for n_dep, dep in enumerate(dependents):
            if n_edges >= 16 or not open_api:
                break
            if n_dep % 2:
                continue
            blocker_item = open_api[(n_dep // 2) % len(open_api)]
            ds.add(
                "dependencies",
                self.stamp(
                    {
                        "id": self.uid("dep-item", blocker_item.row["id"], dep.row["id"]),
                        "from_type": "work_item",
                        "from_id": blocker_item.row["id"],
                        "to_type": "work_item",
                        "to_id": dep.row["id"],
                        "kind": "blocks",
                        "owning_team_id": self.ids["team:payments"],
                        "status": "open",
                    }
                ),
            )
            dep.blockers = max(dep.blockers, 1)
            n_edges += 1
        # Refund status work also waits on specific Payments API endpoints.
        refunds = [i for i in self.items if i.epic.key == "refunds" and i.row["done_at"] is None]
        for n_ref, dep in enumerate(refunds):
            if n_edges >= 16 or not open_api:
                break
            blocker_item = open_api[n_ref % len(open_api)]
            ds.add(
                "dependencies",
                self.stamp(
                    {
                        "id": self.uid("dep-item", blocker_item.row["id"], dep.row["id"]),
                        "from_type": "work_item",
                        "from_id": blocker_item.row["id"],
                        "to_type": "work_item",
                        "to_id": dep.row["id"],
                        "kind": "blocks",
                        "owning_team_id": self.ids["team:payments"],
                        "status": "open",
                    }
                ),
            )
            n_edges += 1

    # ---------------------------------------------------------------- events + metrics
    def _timeline(self, it: _Item) -> list[tuple[datetime, str, str | None, str | None]]:
        row = it.row
        ev: list[tuple[datetime, str, str | None, str | None]] = [
            (row["created_at_src"], "status_change", None, "todo")
        ]
        start: datetime | None = row["started_at"]
        if start is None:
            return ev
        d = it.duration

        def t(frac: float) -> datetime:
            assert start is not None
            return (start + timedelta(days=d * frac)).replace(second=0, microsecond=0)

        ev.append((start, "status_change", "todo", "in_progress"))
        if it.blockers:
            ev.append((t(0.15), "status_change", "in_progress", "blocked"))
            ev.append((t(0.30), "status_change", "blocked", "in_progress"))
        has_pr = row["type"] != "spike"
        for j in range(it.reopens):
            # Early review rejections: within the first days of work, however long the item.
            opened = min(t(0.18 + 0.10 * j), start + timedelta(days=1.5 + 1.5 * j))
            rejected = opened + timedelta(days=min(0.06 * d, 1.0))
            if has_pr:
                ev.append((opened, "pr_opened", None, None))
                ev.append(
                    (
                        opened + timedelta(hours=min(it.review_hours, 0.04 * d * 24)),
                        "pr_reviewed",
                        None,
                        f"{it.review_hours:.1f}",
                    )
                )
            ev.append((opened, "status_change", "in_progress", "in_review"))
            ev.append((rejected, "reopened", "in_review", "in_progress"))
            ev.append((rejected, "status_change", "in_review", "in_progress"))
        final = t(0.45)  # PR opens early; review and QA run until done
        ev.append((final, "status_change", "in_progress", "in_review"))
        if has_pr:
            ev.append((final, "pr_opened", None, None))
            ev.append(
                (
                    final + timedelta(hours=it.review_hours),
                    "pr_reviewed",
                    None,
                    f"{it.review_hours:.1f}",
                )
            )
            ev.append((t(0.97), "pr_merged", None, None))
        ev.append((t(1.0), "status_change", "in_review", "done"))
        n_comments = int(
            self.rng.poisson(1 + 0.6 * row["story_points"] + 1.5 * it.blockers + 1.2 * it.reopens)
        )
        for _ in range(n_comments):
            ev.append((t(self.u(0.0, 1.0)), "comment", None, None))
        if self.rng.random() < 0.05:
            ev.append((t(0.1), "reassigned", None, None))
        return sorted(ev, key=lambda e: e[0])

    def _events_and_metrics(self) -> None:
        ds = self.ds
        actor = {i.row["id"]: i.row["assignee_person_id"] for i in self.items}
        for it in self.items:
            row = it.row
            status = "todo"
            reopen = comments = 0
            review_hours = 0.0
            pr_open_at: datetime | None = None
            for n, (ts, typ, frm, to) in enumerate(self._timeline(it)):
                if ts > self.now:
                    if typ == "pr_reviewed" and pr_open_at is not None:
                        review_hours += max(0.0, (self.now - pr_open_at).total_seconds() / 3600)
                        pr_open_at = None
                    continue
                if typ == "status_change" and to is not None:
                    status = to
                elif typ == "reopened":
                    reopen += 1
                elif typ == "comment":
                    comments += 1
                elif typ == "pr_opened":
                    pr_open_at = ts
                elif typ == "pr_reviewed" and to is not None:
                    review_hours += float(to)
                    pr_open_at = None
                ds.add(
                    "work_item_events",
                    self.stamp(
                        {
                            "id": self.uid("ev", row["id"], n),
                            "work_item_id": row["id"],
                            "event_type": typ,
                            "from_value": frm,
                            "to_value": to,
                            "actor_person_id": actor[row["id"]],
                            "occurred_at": ts,
                        },
                        created=ts,
                    ),
                )
            if pr_open_at is not None:
                review_hours += (self.now - pr_open_at).total_seconds() / 3600
            if row["done_at"] is not None:
                status = "done"
            elif status == "done":
                status = "in_review"
            row.update(
                status=status,
                reopen_count=reopen,
                comments_count=comments,
                pr_review_hours=round(review_hours, 1),
            )
            ds.add("work_items", row)
        self._sprint_totals()
        self._metrics_daily()

    def _sprint_totals(self) -> None:
        by_id = {r["id"]: r for r in self.ds.tables["sprints"]}
        for team in roster.TEAMS:
            for i, s in enumerate(self.sprint_starts):
                lo = datetime.combine(s, time(0), UTC)
                hi = lo + timedelta(days=SPRINT_DAYS)
                items = [it for it in self.items if it.team == team.key and it.sprint == i]
                done_pts = sum(
                    it.row["story_points"]
                    for it in self.items
                    if it.team == team.key
                    and it.row["done_at"] is not None
                    and lo <= it.row["done_at"] < hi
                )
                sp = by_id[self.uid("sprint", team.key, i)]
                sp["committed_points"] = float(sum(it.row["story_points"] for it in items))
                sp["completed_points"] = float(done_pts)
                sp["goal"] = f"Advance {', '.join(sorted({it.epic.title for it in items})[:2])}"

    def _metrics_daily(self) -> None:
        for team in roster.TEAMS:
            items = [it.row for it in self.items if it.team == team.key]
            reviews = [
                (
                    it.row["started_at"]
                    + timedelta(days=it.duration * 0.45, hours=it.review_hours),
                    it.review_hours,
                )
                for it in self.items
                if it.team == team.key
                and it.row["started_at"] is not None
                and it.row["type"] != "spike"
            ]
            for back in range(182, -1, -1):
                day = self.anchor - timedelta(days=back)
                end = datetime.combine(day, time(23, 59), UTC)
                w14, w7 = end - timedelta(days=14), end - timedelta(days=7)
                done14 = [r for r in items if r["done_at"] and w14 < r["done_at"] <= end]
                done7 = [r for r in done14 if r["done_at"] > w7]
                cycle = [(r["done_at"] - r["started_at"]).total_seconds() / 86400 for r in done14]
                rev = [h for ts, h in reviews if w14 < ts <= end]
                wip = sum(
                    1
                    for r in items
                    if r["started_at"]
                    and r["started_at"] <= end
                    and (r["done_at"] is None or r["done_at"] > end)
                )
                bugs = sum(
                    1 for r in items if r["type"] == "bug" and w7 < r["created_at_src"] <= end
                )
                self.ds.add(
                    "metrics_daily",
                    self.stamp(
                        {
                            "id": self.uid("md", team.key, day),
                            "team_id": self.ids[f"team:{team.key}"],
                            "date": day,
                            "velocity": float(sum(r["story_points"] for r in done14)),
                            "throughput": float(len(done7)),
                            "cycle_time_p50": round(float(np.median(cycle)), 2) if cycle else 0.0,
                            "bug_inflow": float(bugs),
                            "review_latency_p50": round(float(np.median(rev)), 2) if rev else 0.0,
                            "wip": float(wip),
                        },
                        created=end,
                    ),
                )

    # ---------------------------------------------------------------- signals, risks, history
    def _signals(self) -> None:
        for team in roster.TEAMS:
            for back in range(182, -1, -1):
                day = self.anchor - timedelta(days=back)
                sentiment = 0.38 + float(self.rng.normal(0, 0.04))
                after_hours = 0.08 + float(self.rng.normal(0, 0.012))
                volume = 120 + float(self.rng.normal(0, 10))
                if team.key == "payments" and back <= 21:
                    progress = (21 - back) / 21
                    sentiment -= 0.33 * progress
                    after_hours += 0.15 * progress
                    volume += 45 * progress
                self.ds.add(
                    "team_signals",
                    self.stamp(
                        {
                            "id": self.uid("sig", team.key, day),
                            "team_id": self.ids[f"team:{team.key}"],
                            "date": day,
                            "sentiment_index": round(sentiment, 3),
                            "message_volume": round(max(volume, 0), 1),
                            "after_hours_ratio": round(min(max(after_hours, 0.0), 1.0), 3),
                        }
                    ),
                )

    def _risks(self) -> None:
        pid = self.ids["program"]
        risks = [
            (
                "Payments API v2 review bottleneck",
                0.7,
                5,
                "vikram",
                "open",
                "manual",
                "PR reviews on Payments API v2 depend on one lead reviewer.",
                "Add a second reviewer rotation from Platform.",
                "pay_api",
            ),
            (
                "Apple Pay certification lead time",
                0.4,
                3,
                "emily",
                "mitigating",
                "manual",
                "Apple merchant certification can take three weeks.",
                "Submit the merchant ID request early.",
                "ios_wallet",
            ),
            (
                "Rate limiter Redis capacity",
                0.3,
                3,
                "ananya",
                "open",
                "manual",
                "Redis cluster sizing is unvalidated at launch peak.",
                "Load-test at 5k RPS before the beta.",
                "rate_limit",
            ),
            (
                "PCI scope expansion from saved cards",
                0.2,
                4,
                "meera",
                "open",
                "manual",
                "Vaulting cards may widen PCI scope.",
                "Use the tokenisation provider.",
                "saved_cards",
            ),
            (
                "Kafka consumer lag during fraud scoring",
                0.25,
                3,
                "marcus",
                "closed",
                "manual",
                "Fraud scoring consumers lagged in load tests.",
                "Partitioned by merchant id.",
                "fraud",
            ),
        ]
        for title, p, impact, owner, status, source, desc, mitig, epic in risks:
            self.ds.add(
                "risks",
                self.stamp(
                    {
                        "id": self.uid("risk", title),
                        "program_id": pid,
                        "title": title,
                        "description": desc,
                        "probability": p,
                        "impact": impact,
                        "owner_person_id": self.ids[f"person:{owner}"],
                        "mitigation": mitig,
                        "status": status,
                        "source": source,
                        "linked_entities": [{"type": "epic", "id": str(self.ids[f"epic:{epic}"])}],
                        "deleted_at": None,
                    },
                    created=self.at(-self.u(10, 120)),
                ),
            )

    def _health_history(self) -> None:
        """Daily health snapshots for the trend line, up to yesterday.

        Today's snapshot is computed live by the health service after models are trained.
        """
        for back in range(60, 0, -1):
            day = self.anchor - timedelta(days=back)
            decline = max(0.0, (28 - back) / 28)
            sched = 92 - 14 * decline + float(self.rng.normal(0, 1.2))
            deps = 85 - 10 * decline + float(self.rng.normal(0, 1.5))
            team = 80 - 6 * decline + float(self.rng.normal(0, 1.0))
            scope = 84 + float(self.rng.normal(0, 1.0))
            quality = 82 - 4 * decline + float(self.rng.normal(0, 1.0))
            subs = {
                k: round(min(max(v, 0), 100), 1)
                for k, v in (
                    ("schedule", sched),
                    ("scope", scope),
                    ("quality", quality),
                    ("dependencies", deps),
                    ("team", team),
                )
            }
            score = (
                0.30 * subs["schedule"]
                + 0.20 * subs["scope"]
                + 0.20 * subs["quality"]
                + 0.15 * subs["dependencies"]
                + 0.15 * subs["team"]
            )
            self.ds.add(
                "health_snapshots",
                self.stamp(
                    {
                        "id": self.uid("health", day),
                        "program_id": self.ids["program"],
                        "date": day,
                        "score": round(score, 1),
                        "subscores": subs,
                        "drivers": [],
                    }
                ),
            )

    def _persona_and_policies(self) -> None:
        priya = self.ids["user:priya"]
        self.ds.add(
            "persona_profiles",
            self.stamp(
                {
                    "id": self.uid("persona", "priya"),
                    "user_id": priya,
                    "priorities": [
                        "Hit the public launch date",
                        "Protect team health",
                        "Keep executives ahead of surprises",
                        "Quality over scope",
                    ],
                    "style_examples": [
                        "Bottom line: we are on track for launch, with one risk I want you "
                        "to see early.",
                        "Ask: approve two Platform engineers pairing on Payments API v2 "
                        "for two sprints.",
                        "No surprises: the forecast moved 4 days this week; here is why "
                        "and what we do.",
                    ],
                    "tone": "concise",
                    "risk_tolerance": "low",
                    "escalation_rules": [
                        {
                            "when": "launch P80 slips more than 5 days",
                            "then": "notify Rahul the same day",
                        },
                        {
                            "when": "a person is above 100% utilisation for 2 sprints",
                            "then": "raise with their EM",
                        },
                    ],
                    "working_hours": {"start": "09:00", "end": "18:00", "timezone": "Asia/Kolkata"},
                    "delegation_weights": {},
                }
            ),
        )
        for key in ("arjun", "grace", "david", "fatima", "rahul"):
            self.ds.add(
                "persona_profiles",
                self.stamp(
                    {
                        "id": self.uid("persona", key),
                        "user_id": self.ids[f"user:{key}"],
                        "priorities": [],
                        "style_examples": [],
                        "tone": "concise",
                        "risk_tolerance": "medium",
                        "escalation_rules": [],
                        "working_hours": {},
                        "delegation_weights": {},
                    }
                ),
            )

    def _integrations(self) -> None:
        for provider in ("jira", "github", "slack", "gcal", "confluence"):
            self.ds.add(
                "integrations",
                self.stamp(
                    {
                        "id": self.uid("integration", provider),
                        "provider": provider,
                        "mode": "mock",
                        "config": {},
                        "last_sync_at": self.at(-0.1),
                        "status": "connected",
                    }
                ),
            )


def generate(seed: int = 42, anchor: date | None = None) -> Dataset:
    from twinpm.seed.content_gen import add_content

    gen = Generator(seed, anchor or datetime.now(UTC).date())
    ds = gen.build()
    add_content(gen)
    return ds
