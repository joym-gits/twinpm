# ADR 0003: Offline-first embeddings

Status: accepted

## Context
The spec names `sentence-transformers` (`all-MiniLM-L6-v2`, 384-dim). It pulls in PyTorch
(hundreds of MB) and downloads the model from Hugging Face on first use, which breaks the
"demo works fully offline" requirement and bloats the API image.

## Decision
`sentence-transformers` is an optional extra (`uv sync --extra embeddings`). When it is
installed and the model is in the local cache, TwinPM uses it. Otherwise it uses a
deterministic 384-dim feature-hashing embedder (word unigrams, bigrams and character
trigrams; signed hashing; L2-normalised). Both write the same `VECTOR(384)` columns.

## Consequences
- The demo and CI run offline with no model download.
- Hashing embeddings are lexical, not semantic. Hybrid retrieval (vector + full-text + graph
  boost, fused with RRF) compensates; theme clustering on hashed vectors is good enough for
  the seeded feedback, whose themes are lexically distinct.
- Switching embedders requires re-indexing (`make seed` re-indexes everything).
