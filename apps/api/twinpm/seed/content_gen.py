"""Turn the static content in `content.py` into document, decision and feedback rows."""

from __future__ import annotations

import math
from datetime import timedelta
from typing import TYPE_CHECKING

from twinpm.seed.content import DECISIONS, DESIGN_DOCS, FEEDBACK_THEMES, MEETING_NOTES

if TYPE_CHECKING:
    from twinpm.seed.generator import Generator

SOURCES = ["support", "sales", "survey", "interview"]
SOURCE_P = [0.45, 0.2, 0.25, 0.1]


def add_content(gen: Generator) -> None:
    ds, rng = gen.ds, gen.rng
    pid = gen.ids["program"]
    for doc in [*DESIGN_DOCS, *MEETING_NOTES]:
        did = gen.ids[f"doc:{doc['key']}"] = gen.uid("doc", doc["key"])
        when = gen.at(-doc["days_ago"])
        ds.add(
            "documents",
            gen.stamp(
                {
                    "id": did,
                    "program_id": pid,
                    "type": doc["type"],
                    "title": doc["title"],
                    "body": doc["body"],
                    "author_person_id": gen.ids[f"person:{doc['author']}"],
                    "source_url": f"https://docs.novapay.example/{doc['key']}",
                    "occurred_at": when,
                    "deleted_at": None,
                },
                created=when,
            ),
        )
    for d in DECISIONS:
        when = gen.at(-d["days_ago"])
        ds.add(
            "decisions",
            gen.stamp(
                {
                    "id": gen.uid("decision", d["key"]),
                    "program_id": pid,
                    "title": d["title"],
                    "context": d["context"],
                    "options": [dict(o) for o in d["options"]],
                    "chosen_option": d["chosen_option"],
                    "rationale": d["rationale"],
                    "participants": [gen.ids[f"person:{p}"] for p in d["participants"]],
                    "decided_at": when,
                    "source_document_id": gen.ids[f"doc:{d['source_doc']}"]
                    if d["source_doc"]
                    else None,
                    "deleted_at": None,
                },
                created=when,
            ),
        )
    n = 0
    for key, theme in FEEDBACK_THEMES.items():
        sentences = list(theme["sentences"])
        order = rng.permutation(len(sentences))
        for i in range(theme["count"]):
            u = float(rng.random())
            frac = {"rising": 1 - math.sqrt(u), "falling": math.sqrt(u)}.get(theme["growth"], u)
            sentiment = float(rng.normal(theme["sentiment_mean"], theme["sentiment_sd"]))
            when = gen.at(-(1 + 181 * frac))
            ds.add(
                "feedback_items",
                gen.stamp(
                    {
                        "id": gen.uid("feedback", key, i),
                        "source": str(rng.choice(SOURCES, p=SOURCE_P)),
                        "customer_segment": str(rng.choice(theme["segments"])),
                        "text": sentences[int(order[i % len(sentences)])],
                        "sentiment": round(min(max(sentiment, -1.0), 1.0), 3),
                        "theme_id": None,
                        "received_at": when,
                        "embedding": None,
                    },
                    created=when + timedelta(minutes=n),
                ),
            )
            n += 1
