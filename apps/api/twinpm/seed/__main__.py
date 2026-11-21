"""`python -m twinpm.seed --seed 42`: reset the NovaPay demo org and print a summary."""

from __future__ import annotations

import argparse
import asyncio
from datetime import date

from twinpm.config import get_settings
from twinpm.db.session import get_engine, get_sessionmaker
from twinpm.seed.generator import generate
from twinpm.seed.loader import load


async def run(seed: int, anchor: date | None) -> None:
    ds = generate(seed, anchor)
    async with get_sessionmaker()() as session:
        timing = await load(session, ds, get_settings().seed_demo_password.get_secret_value())
    await get_engine().dispose()
    open_items = sum(1 for r in ds.tables["work_items"] if r["status"] != "done")
    print(f"\nTwinPM demo seed  (seed={seed}, anchor={ds.anchor}, digest={ds.digest()[:16]})")
    print(f"{'table':<22}{'rows':>8}")
    print("-" * 30)
    for table, n in ds.counts().items():
        print(f"{table:<22}{n:>8}")
    print("-" * 30)
    print(f"open work items: {open_items}   loaded in {timing['seconds']}s\n")


def main() -> None:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--seed", type=int, default=42)
    p.add_argument("--anchor", type=date.fromisoformat, default=None, help="YYYY-MM-DD")
    args = p.parse_args()
    asyncio.run(run(args.seed, args.anchor))


if __name__ == "__main__":
    main()
