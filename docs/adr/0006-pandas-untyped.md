# ADR 0006: pandas is treated as untyped under mypy --strict

Status: accepted

`pandas-stubs` types every scalar access as a large union, which produced over a hundred
false positives across the ML modules and pushed the code toward casts that add nothing. We
removed `pandas-stubs` and list `pandas.*` under `ignore_missing_imports`, so mypy `--strict`
still checks all of our own signatures while pandas values are `Any`. ML behaviour is covered
by tests (`tests/test_ml.py`) instead.
