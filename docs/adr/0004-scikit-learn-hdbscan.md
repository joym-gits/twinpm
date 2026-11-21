# ADR 0004: scikit-learn HDBSCAN instead of the `hdbscan` package

Status: accepted

scikit-learn ships `sklearn.cluster.HDBSCAN` (since 1.3). It removes a native dependency
that often fails to build on new Python versions. KMeans with silhouette-selected k remains
the fallback when HDBSCAN labels most points as noise.
