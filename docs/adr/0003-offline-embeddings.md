# ADR 0003: Embeddings — MiniLM by default, hashing fallback

Status: accepted (revised)

## Context
The spec names `sentence-transformers` (`all-MiniLM-L6-v2`, 384-dim). It pulls in PyTorch
and downloads the model from Hugging Face on first use, which conflicts with running the
demo offline.

## Decision
- `sentence-transformers` is a core dependency. Linux installs use the CPU-only PyTorch index
  (`[tool.uv.sources]`), which keeps the image smaller.
- The model is downloaded at build time (`python -m twinpm.rag.embedding` in the Dockerfile and
  `make install`) and loaded with `local_files_only=True`, so the running app never needs the
  network.
- If the model is unavailable, TwinPM falls back to a deterministic 384-dim feature-hashing
  embedder. Both write the same `VECTOR(384)` columns.

## Evidence
Against the seed's known feedback themes, KMeans(k=6) gives an adjusted Rand index of 0.93 on
MiniLM embeddings, 0.34–0.44 on hashing or TF-IDF/LSA vectors.

## Consequences
The API image grows by roughly 1 GB (CPU torch plus the model). Re-index after switching
embedders (`make seed`).
