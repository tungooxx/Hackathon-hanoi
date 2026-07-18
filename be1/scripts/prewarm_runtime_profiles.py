"""Precompile valid runtime decision profiles for the current Elasticsearch catalog.

Run from ``be1``:
    .venv\\Scripts\\python.exe scripts\\prewarm_runtime_profiles.py --concurrency 2
"""
from __future__ import annotations

import argparse
import asyncio
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app import ontology, product_repo
from app.profile_compiler import compile_profile, get_cached_profile


async def main() -> int:
    parser = argparse.ArgumentParser(description="Prewarm catalog runtime profiles")
    parser.add_argument("--concurrency", type=int, default=2)
    parser.add_argument("--timeout", type=float, default=90.0)
    args = parser.parse_args()
    if args.concurrency <= 0 or args.timeout <= 0:
        parser.error("--concurrency and --timeout must be positive")

    categories = await product_repo.list_categories()
    semaphore = asyncio.Semaphore(args.concurrency)
    started = time.perf_counter()
    counts = {"cached": 0, "compiled": 0, "empty": 0, "failed": 0}

    async def prewarm(category: str) -> tuple[str, str, str]:
        async with semaphore:
            try:
                products = await product_repo.get_products(category)
                if not products:
                    return category, "empty", ""
                if get_cached_profile(category, products) is not None:
                    return category, "cached", ""
                profile = await asyncio.wait_for(
                    compile_profile(category, ontology.questions_for_category(category), products),
                    timeout=args.timeout,
                )
                return category, "compiled", str(len(profile.questions))
            except Exception as error:
                return category, "failed", f"{type(error).__name__}: {error}"

    for completed in asyncio.as_completed([prewarm(category) for category in categories]):
        category, status, detail = await completed
        counts[status] += 1
        suffix = f" ({detail} questions)" if status == "compiled" else (f": {detail}" if detail else "")
        print(f"[{sum(counts.values())}/{len(categories)}] {status}: {category}{suffix}", flush=True)

    elapsed = round(time.perf_counter() - started, 1)
    print(f"Done in {elapsed}s: {counts}", flush=True)
    return 1 if counts["failed"] else 0


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")
    raise SystemExit(asyncio.run(main()))
