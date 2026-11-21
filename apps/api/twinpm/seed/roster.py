"""NovaPay roster: teams, people, skills and users for the Checkout 2.0 demo."""

from __future__ import annotations

from dataclasses import dataclass, field

ORG_NAME = "NovaPay"
ORG_SLUG = "novapay"
EMAIL_DOMAIN = "novapay.example"


@dataclass(frozen=True)
class PersonSpec:
    key: str
    name: str
    title: str
    team: str | None
    skills: dict[str, int]
    capacity: float = 40.0
    timezone: str = "Asia/Kolkata"
    growth_goals: tuple[str, ...] = ()
    role: str | None = None  # set when the person is also a TwinPM user


@dataclass(frozen=True)
class TeamSpec:
    key: str
    name: str
    description: str
    prefix: str
    manager: str
    base_review_hours: float
    base_velocity: float  # points per sprint for the whole team
    members: list[str] = field(default_factory=list)


SKILL_CATEGORIES = {
    "go": "language",
    "python": "language",
    "react-native": "mobile",
    "ios": "mobile",
    "android": "mobile",
    "kafka": "infrastructure",
    "postgres": "data",
    "oauth": "security",
    "payments-compliance": "domain",
    "k8s": "infrastructure",
    "observability": "infrastructure",
    "api-design": "architecture",
}

TEAMS = [
    TeamSpec(
        "platform",
        "Platform",
        "Shared infrastructure, resilience and developer platform.",
        "PLAT",
        "grace",
        7.0,
        52.0,
    ),
    TeamSpec(
        "payments",
        "Payments",
        "Payment processing, ledger, compliance and payment APIs.",
        "PAY",
        "david",
        8.0,
        54.0,
    ),
    TeamSpec(
        "mobile",
        "Mobile",
        "iOS and Android apps, including the checkout experience.",
        "MOB",
        "fatima",
        7.5,
        50.0,
    ),
]

PEOPLE = [
    # Platform
    PersonSpec(
        "ananya",
        "Ananya Iyer",
        "Staff Engineer, Platform Lead",
        "platform",
        {"k8s": 5, "go": 4, "observability": 4, "kafka": 3},
        40,
        growth_goals=("architecture leadership",),
    ),
    PersonSpec(
        "karan",
        "Karan Malhotra",
        "Senior Software Engineer",
        "platform",
        {"go": 5, "api-design": 5, "k8s": 3, "postgres": 3, "kafka": 2},
        40,
        growth_goals=("payments", "api-design"),
    ),
    PersonSpec(
        "liwei",
        "Li Wei",
        "Senior Software Engineer",
        "platform",
        {"postgres": 5, "python": 4, "go": 3, "observability": 3},
        36,
        timezone="Asia/Singapore",
        growth_goals=("payments", "data modelling"),
    ),
    PersonSpec(
        "marcus",
        "Marcus Johnson",
        "Software Engineer",
        "platform",
        {"observability": 4, "kafka": 4, "go": 3},
        40,
        timezone="America/New_York",
        growth_goals=("k8s",),
    ),
    PersonSpec(
        "sofia",
        "Sofia Martinez",
        "Software Engineer",
        "platform",
        {"python": 4, "k8s": 3, "postgres": 2},
        32,
        timezone="Europe/Madrid",
        growth_goals=("observability",),
    ),
    # Payments
    PersonSpec(
        "vikram",
        "Vikram Rao",
        "Lead Engineer, Payments",
        "payments",
        {"go": 5, "payments-compliance": 5, "api-design": 4, "kafka": 4, "oauth": 3},
        40,
        growth_goals=("engineering management",),
    ),
    PersonSpec(
        "meera",
        "Meera Nair",
        "Senior Software Engineer",
        "payments",
        {"payments-compliance": 4, "python": 4, "postgres": 3},
        40,
        growth_goals=("api-design",),
    ),
    PersonSpec(
        "daniel",
        "Daniel Okafor",
        "Software Engineer",
        "payments",
        {"go": 3, "kafka": 3, "postgres": 2},
        40,
        timezone="Europe/London",
        growth_goals=("payments-compliance",),
    ),
    PersonSpec(
        "aisha",
        "Aisha Khan",
        "Software Engineer",
        "payments",
        {"oauth": 4, "api-design": 3, "go": 2},
        36,
        timezone="Asia/Dubai",
        growth_goals=("security",),
    ),
    PersonSpec(
        "tom",
        "Tom Becker",
        "Software Engineer",
        "payments",
        {"python": 3, "postgres": 3, "observability": 2},
        40,
        timezone="Europe/Berlin",
        growth_goals=("go",),
    ),
    # Mobile
    PersonSpec(
        "rohan",
        "Rohan Gupta",
        "Mobile Lead",
        "mobile",
        {"react-native": 5, "ios": 4, "api-design": 3},
        40,
        growth_goals=("product sense",),
    ),
    PersonSpec(
        "emily",
        "Emily Chen",
        "Senior iOS Engineer",
        "mobile",
        {"ios": 5, "react-native": 4},
        40,
        timezone="America/Los_Angeles",
        growth_goals=("android",),
    ),
    PersonSpec(
        "kwame",
        "Kwame Mensah",
        "Senior Android Engineer",
        "mobile",
        {"android": 5, "react-native": 3, "kafka": 1},
        40,
        timezone="Africa/Accra",
        growth_goals=("ios",),
    ),
    PersonSpec(
        "neha",
        "Neha Joshi",
        "Software Engineer, Mobile",
        "mobile",
        {"react-native": 4, "api-design": 2, "ios": 2},
        36,
        growth_goals=("api-design",),
    ),
    PersonSpec(
        "lucas",
        "Lucas Silva",
        "Software Engineer, Mobile",
        "mobile",
        {"android": 4, "ios": 3, "react-native": 2},
        40,
        timezone="America/Sao_Paulo",
        growth_goals=("react-native",),
    ),
    # Leadership and product (TwinPM users; not part of team capacity)
    PersonSpec(
        "priya",
        "Priya Sharma",
        "Senior Technical Program Manager",
        None,
        {"api-design": 2},
        40,
        role="tpm",
    ),
    PersonSpec(
        "arjun", "Arjun Mehta", "Technical Product Manager", None, {"api-design": 2}, 40, role="tpm"
    ),
    PersonSpec(
        "grace",
        "Grace Lee",
        "Engineering Manager, Platform",
        None,
        {"k8s": 3},
        40,
        timezone="America/New_York",
        role="eng_manager",
    ),
    PersonSpec(
        "david",
        "David Kim",
        "Engineering Manager, Payments",
        None,
        {"payments-compliance": 3},
        40,
        role="eng_manager",
    ),
    PersonSpec(
        "fatima",
        "Fatima Al-Sayed",
        "Engineering Manager, Mobile",
        None,
        {"react-native": 3},
        40,
        timezone="Asia/Dubai",
        role="eng_manager",
    ),
    PersonSpec("rahul", "Rahul Verma", "VP Engineering", None, {}, 40, role="executive"),
]

# Org admin is a user without a workforce record.
ADMIN = ("admin", "Sam Taylor", "org_admin")


def team_members(team_key: str) -> list[PersonSpec]:
    return [p for p in PEOPLE if p.team == team_key]


def email_for(key: str) -> str:
    return f"{key}@{EMAIL_DOMAIN}"
