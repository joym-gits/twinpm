"""Program structure for Checkout 2.0: objectives, initiatives, epics and epic dependencies."""

from __future__ import annotations

from dataclasses import dataclass

PROGRAM_NAME = "Checkout 2.0"
PROGRAM_OBJECTIVE = (
    "Ship a faster, safer checkout across web and mobile: one payments API, resilient "
    "infrastructure and a redesigned mobile flow, launched publicly to all NovaPay merchants."
)
LAUNCH_NAME = "Public Launch"
LAUNCH_WEEKS_OUT = 16


@dataclass(frozen=True)
class ObjectiveSpec:
    key: str
    title: str
    key_results: tuple[str, ...]


@dataclass(frozen=True)
class InitiativeSpec:
    key: str
    title: str
    objective: str
    bucket: str
    description: str
    reach: float
    impact: float
    confidence: float
    effort: float
    wsjf: tuple[
        float, float, float, float
    ]  # business value, time criticality, risk reduction, size


@dataclass(frozen=True)
class EpicSpec:
    key: str
    title: str
    team: str
    initiative: str
    launch: bool
    # Share of the team's sprint work that lands on this epic, by period.
    weight_history: float
    weight_recent: float
    backlog_items: int  # unstarted items in the backlog at "today"
    labels: tuple[str, ...]
    skills: tuple[str, ...]
    status: str = "in_progress"


OBJECTIVES = [
    ObjectiveSpec(
        "o1",
        "Launch Checkout 2.0 to all merchants",
        ("Public launch on the target date", "95% of merchants migrated within 60 days"),
    ),
    ObjectiveSpec(
        "o2",
        "Cut payment failures in half",
        ("Payment failure rate below 1.2%", "p99 authorisation latency under 800 ms"),
    ),
    ObjectiveSpec(
        "o3",
        "Grow mobile checkout conversion",
        ("Mobile conversion +8 percentage points", "Checkout steps reduced from 5 to 3"),
    ),
    ObjectiveSpec(
        "o4",
        "Meet the compliance and reliability bar",
        ("Zero P1 compliance findings", "99.95% checkout availability"),
    ),
]

INITIATIVES = [
    InitiativeSpec(
        "i1",
        "Payments API v2",
        "o2",
        "now",
        "One idempotent, versioned payments API for web, mobile and partners.",
        9000,
        3,
        0.8,
        8,
        (9, 9, 8, 8),
    ),
    InitiativeSpec(
        "i2",
        "Unified mobile checkout",
        "o3",
        "now",
        "Redesigned three-step mobile checkout with wallets.",
        7000,
        3,
        0.8,
        6,
        (8, 8, 4, 6),
    ),
    InitiativeSpec(
        "i3",
        "Resilience and rate limiting",
        "o4",
        "now",
        "Rate limiting, idempotency and graceful degradation at the edge.",
        9000,
        2,
        0.9,
        4,
        (7, 7, 9, 4),
    ),
    InitiativeSpec(
        "i4",
        "Fraud detection hooks",
        "o4",
        "now",
        "Pre-authorisation fraud scoring hooks for partners.",
        5000,
        2,
        0.7,
        4,
        (6, 6, 8, 4),
    ),
    InitiativeSpec(
        "i5",
        "Observability uplift",
        "o4",
        "next",
        "Tracing, SLOs and alerting for the checkout path.",
        9000,
        1,
        0.9,
        3,
        (5, 4, 7, 3),
    ),
    InitiativeSpec(
        "i6",
        "Saved cards and UPI autopay",
        "o3",
        "next",
        "Card vaulting and UPI autopay mandates.",
        6000,
        2,
        0.6,
        6,
        (7, 5, 3, 6),
    ),
    InitiativeSpec(
        "i7",
        "Multi-currency pricing",
        "o1",
        "later",
        "Display and settle in 12 currencies.",
        2500,
        2,
        0.5,
        8,
        (5, 3, 2, 8),
    ),
    InitiativeSpec(
        "i8",
        "Bulk export and reporting",
        "o1",
        "later",
        "Merchant bulk export of transactions and settlements.",
        4000,
        2,
        0.7,
        3,
        (6, 4, 2, 3),
    ),
]

EPICS = [
    # Launch scope
    EpicSpec(
        "pay_api",
        "Payments API v2",
        "payments",
        "i1",
        True,
        0.20,
        0.55,
        11,
        ("payments-api", "backend"),
        ("go", "api-design", "payments-compliance", "postgres"),
    ),
    EpicSpec(
        "idem",
        "Idempotency keys",
        "payments",
        "i3",
        True,
        0.10,
        0.15,
        4,
        ("payments-api", "backend"),
        ("postgres", "go", "api-design"),
    ),
    EpicSpec(
        "mob_ui",
        "Mobile checkout UI",
        "mobile",
        "i2",
        True,
        0.25,
        0.60,
        4,
        ("mobile", "checkout"),
        ("react-native", "ios", "android"),
    ),
    EpicSpec(
        "ios_wallet",
        "iOS wallet integration",
        "mobile",
        "i2",
        True,
        0.05,
        0.20,
        1,
        ("mobile", "ios"),
        ("ios", "react-native"),
    ),
    EpicSpec(
        "android_wallet",
        "Android wallet integration",
        "mobile",
        "i2",
        True,
        0.05,
        0.20,
        1,
        ("mobile", "android"),
        ("android", "react-native"),
    ),
    EpicSpec(
        "rate_limit",
        "Platform rate limiter",
        "platform",
        "i3",
        True,
        0.15,
        0.35,
        3,
        ("platform", "resilience"),
        ("go", "k8s", "api-design"),
    ),
    EpicSpec(
        "fraud",
        "Fraud hooks",
        "platform",
        "i4",
        True,
        0.10,
        0.30,
        5,
        ("platform", "fraud"),
        ("go", "kafka", "api-design"),
    ),
    EpicSpec(
        "obs",
        "Checkout observability",
        "platform",
        "i5",
        True,
        0.10,
        0.20,
        5,
        ("platform", "observability"),
        ("observability", "k8s"),
    ),
    # History and future work
    EpicSpec(
        "ledger",
        "Ledger migration",
        "payments",
        "i1",
        False,
        0.35,
        0.0,
        0,
        ("payments", "data"),
        ("postgres", "payments-compliance"),
        "done",
    ),
    EpicSpec(
        "refunds",
        "Refund status API",
        "payments",
        "i1",
        False,
        0.20,
        0.10,
        10,
        ("payments-api", "refunds"),
        ("go", "api-design"),
    ),
    EpicSpec(
        "saved_cards",
        "Saved cards vault",
        "payments",
        "i6",
        False,
        0.15,
        0.10,
        8,
        ("payments", "cards"),
        ("payments-compliance", "go"),
        "planned",
    ),
    EpicSpec(
        "kafka",
        "Event streaming backbone",
        "platform",
        "i5",
        False,
        0.30,
        0.0,
        0,
        ("platform", "kafka"),
        ("kafka", "go"),
        "done",
    ),
    EpicSpec(
        "retention",
        "Data retention controls",
        "platform",
        "i5",
        False,
        0.20,
        0.05,
        1,
        ("platform", "data"),
        ("postgres", "python"),
    ),
    EpicSpec(
        "bulk_export",
        "Bulk export service",
        "platform",
        "i8",
        False,
        0.15,
        0.10,
        8,
        ("platform", "export"),
        ("python", "postgres"),
        "planned",
    ),
    EpicSpec(
        "mob_ds",
        "Mobile design system",
        "mobile",
        "i2",
        False,
        0.40,
        0.0,
        0,
        ("mobile", "design-system"),
        ("react-native",),
        "done",
    ),
    EpicSpec(
        "dark_mode",
        "Dark mode",
        "mobile",
        "i2",
        False,
        0.15,
        0.0,
        5,
        ("mobile", "ui"),
        ("react-native", "ios", "android"),
        "planned",
    ),
    EpicSpec(
        "upi",
        "UPI autopay mandates",
        "payments",
        "i6",
        False,
        0.0,
        0.10,
        8,
        ("payments", "upi"),
        ("payments-compliance", "go"),
        "planned",
    ),
    EpicSpec(
        "fx",
        "Multi-currency pricing",
        "payments",
        "i7",
        False,
        0.0,
        0.0,
        5,
        ("payments", "fx"),
        ("payments-compliance", "python"),
        "planned",
    ),
]

# Epic-level "blocks" edges: (blocker, blocked).
EPIC_DEPENDENCIES = [
    ("pay_api", "mob_ui"),
    ("pay_api", "rate_limit"),
    ("pay_api", "fraud"),
    ("idem", "pay_api"),
    ("pay_api", "ios_wallet"),
    ("pay_api", "android_wallet"),
    ("rate_limit", "obs"),
    ("kafka", "fraud"),
    ("pay_api", "refunds"),
]
LAUNCH_EPICS = [e.key for e in EPICS if e.launch]
