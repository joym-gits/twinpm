"""7.5 Theme clustering (HDBSCAN, KMeans fallback) and transparent opportunity scoring."""

from __future__ import annotations

import re
from collections import Counter
from dataclasses import dataclass, field
from datetime import timedelta
from typing import Any

import numpy as np
import pandas as pd
from sklearn.cluster import HDBSCAN, KMeans
from sklearn.metrics import silhouette_score

from twinpm.ml.data import ProgramData
from twinpm.rag.embedding import STOPWORDS, embed

SEGMENT_VALUE = {"enterprise": 1.0, "partner": 0.8, "smb": 0.6, "consumer": 0.4}
OPPORTUNITY_WEIGHTS = {
    "volume": 0.30,
    "growth": 0.20,
    "severity": 0.20,
    "segment_value": 0.15,
    "strategic_fit": 0.15,
}
EXTRA_STOP = STOPWORDS | {
    "we",
    "us",
    "our",
    "need",
    "would",
    "like",
    "want",
    "please",
    "really",
    "customer",
    "customers",
    "users",
    "app",
    "novapay",
    "still",
    "when",
    "there",
    "they",
    "them",
    "been",
    "more",
    "very",
    "into",
    "only",
    "every",
    "than",
    "also",
    "what",
    "which",
    "about",
    "make",
    "being",
}
_WORD = re.compile(r"[a-z][a-z\-]+")


@dataclass
class ThemeResult:
    label: str
    summary: str
    keywords: list[str]
    member_ids: list[Any]
    avg_sentiment: float
    opportunity: dict[str, Any]
    quotes: list[str] = field(default_factory=list)


def _cluster(vecs: np.ndarray) -> tuple[np.ndarray, str]:
    labels = HDBSCAN(min_cluster_size=8, min_samples=3, metric="euclidean").fit_predict(vecs)
    n = len(set(labels) - {-1})
    if n >= 3 and (labels == -1).mean() <= 0.35:
        return labels, "hdbscan"
    best, best_k, best_s = None, 0, -1.0
    for k in range(4, 8):
        lab = KMeans(n_clusters=k, n_init=10, random_state=42).fit_predict(vecs)
        s = float(silhouette_score(vecs, lab))
        if s > best_s:
            best, best_k, best_s = lab, k, s
    assert best is not None
    return best, f"kmeans(k={best_k}, silhouette={best_s:.3f})"


def ctfidf_keywords(docs_by_cluster: dict[int, list[str]], top: int = 4) -> dict[int, list[str]]:
    """Class-based TF-IDF: terms frequent in one cluster and rare across clusters."""
    tf = {
        c: Counter(
            w for d in docs for w in _WORD.findall(d.lower()) if w not in EXTRA_STOP and len(w) > 2
        )
        for c, docs in docs_by_cluster.items()
    }
    df = Counter(w for counts in tf.values() for w in counts)
    n = len(tf)
    out = {}
    for c, counts in tf.items():
        total = sum(counts.values()) or 1
        scores = {w: (k / total) * np.log(1 + n / df[w]) for w, k in counts.items()}
        out[c] = [w for w, _ in sorted(scores.items(), key=lambda kv: -kv[1])[:top]]
    return out


def compute(
    data: ProgramData, objective_titles: list[str] | None = None
) -> tuple[list[ThemeResult], str]:
    fb = data.feedback.reset_index(drop=True)
    if fb.empty:
        return [], "none"
    vecs = embed(fb["text"].tolist())
    labels, method = _cluster(vecs)
    clusters = sorted(set(labels) - {-1})
    kw = ctfidf_keywords({c: fb.loc[labels == c, "text"].tolist() for c in clusters})
    obj = embed(objective_titles or data.objectives["title"].tolist())
    now = pd.Timestamp(data.now)
    max_size = max(int((labels == c).sum()) for c in clusters)
    results = []
    for c in clusters:
        mask = labels == c
        g = fb[mask]
        centroid = vecs[mask].mean(axis=0)
        centroid /= np.linalg.norm(centroid) or 1.0
        recent = (g["received_at"] > now - timedelta(days=60)).mean()
        growth = float(np.clip(recent / (60 / 182) / 2, 0, 1))  # 1.0 = twice the expected share
        sentiment = float(g["sentiment"].mean())
        parts = {
            "volume": round(len(g) / max_size, 3),
            "growth": round(growth, 3),
            "severity": round((1 - sentiment) / 2, 3),
            "segment_value": round(
                float(g["customer_segment"].map(SEGMENT_VALUE).fillna(0.5).mean()), 3
            ),
            "strategic_fit": round(
                float(np.clip((obj @ centroid).max() * 2, 0, 1)) if len(obj) else 0.5, 3
            ),
        }
        score = round(100 * sum(OPPORTUNITY_WEIGHTS[k] * v for k, v in parts.items()), 1)
        words = kw.get(c, [])
        label = " / ".join(w.replace("-", " ").title() for w in words[:2]) or f"Theme {c + 1}"
        dist = vecs[mask] @ centroid
        quotes = g.iloc[np.argsort(-dist)[:3]]["text"].tolist()
        results.append(
            ThemeResult(
                label,
                f"{len(g)} items about {', '.join(words)}; average sentiment {sentiment:+.2f}.",
                words,
                g["id"].tolist(),
                round(sentiment, 3),
                {"score": score, "breakdown": parts, "weights": OPPORTUNITY_WEIGHTS},
                quotes,
            )
        )
    results.sort(key=lambda t: -t.opportunity["score"])
    return results, method
