#!/usr/bin/env python3
"""Upload scorer_results to a Noveum dataset.

POST /api/v1/scorers/results/batch — camelCase fields, boolean `passed`,
object `metadata`. The items POST endpoint does NOT carry scorer_results.
"""

from __future__ import annotations

import argparse
import json
import logging
import os
import sys
import time
from pathlib import Path
from typing import Any

import requests

sys.path.insert(0, str(Path(__file__).resolve().parent))
from _common import auth_kwargs, resolve_api_key  # noqa: E402

BASE_URL = os.getenv("NOVEUM_BASE_URL", "https://noveum.ai")


def _parse_metadata(v: Any) -> dict:
    if isinstance(v, dict):
        return v
    if isinstance(v, str) and v.strip():
        try:
            p = json.loads(v)
            return p if isinstance(p, dict) else {"value": p}
        except (json.JSONDecodeError, ValueError):
            return {"raw": v}
    return {}


def to_api_result(slug: str, item_id: str, sr: dict) -> dict:
    name = sr.get("scorer_name") or sr.get("scorer_id") or "unknown"
    scorer_id = sr.get("scorer_id") or f"{name}_scorer"
    passed_raw = sr.get("passed")
    if isinstance(passed_raw, bool):
        passed = passed_raw
    else:
        try:
            passed = bool(int(passed_raw))
        except (TypeError, ValueError):
            passed = False
    try:
        score = float(sr.get("score"))
    except (TypeError, ValueError):
        score = -1.0
    return {
        "datasetSlug": slug,
        "itemId": item_id,
        "scorerId": scorer_id,
        "scorerName": name,
        "score": score,
        "passed": passed,
        "reasoning": sr.get("reasoning") or "",
        "metadata": _parse_metadata(sr.get("metadata")),
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", type=Path, required=True)
    parser.add_argument("--slug", required=True)
    parser.add_argument("--batch-size", type=int, default=100)
    parser.add_argument(
        "--exclude-scorers", nargs="*", default=[], help="Scorer names to skip."
    )
    parser.add_argument(
        "--include-scorers",
        nargs="*",
        default=None,
        help="Only upload these scorer names (defaults to all).",
    )
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--api-key", default=None)
    parser.add_argument("--env-key", default=None)
    parser.add_argument("--env-file", type=Path, default=None)
    args = parser.parse_args()

    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s - %(levelname)s - %(message)s",
        datefmt="%H:%M:%S",
        stream=sys.stderr,
        force=True,
    )
    log = logging.getLogger("upload_scorer_results")

    raw_items = json.loads(args.input.read_text(encoding="utf-8"))
    log.info("Loaded %d items from %s", len(raw_items), args.input)

    skip = set(args.exclude_scorers)
    only = set(args.include_scorers) if args.include_scorers else None

    payload: list[dict] = []
    for it in raw_items:
        item_id = it.get("item_id")
        if not item_id:
            continue
        for sr in it.get("scorer_results") or []:
            name = sr.get("scorer_name") or sr.get("scorer_id")
            if not name or name in skip:
                continue
            if only is not None and name not in only:
                continue
            payload.append(to_api_result(args.slug, item_id, sr))

    log.info("Prepared %d scorer-result rows", len(payload))
    if args.dry_run:
        print(json.dumps(payload[:2], indent=2, default=str))
        return 0
    if not payload:
        log.warning("Nothing to upload.")
        return 0

    key = resolve_api_key(args.api_key, args.env_key, args.env_file)
    auth = auth_kwargs(key)
    url = f"{BASE_URL}/api/v1/scorers/results/batch"

    created = failed = 0
    total_batches = (len(payload) + args.batch_size - 1) // args.batch_size
    for i in range(0, len(payload), args.batch_size):
        batch = payload[i : i + args.batch_size]
        t0 = time.monotonic()
        r = requests.post(url, json={"results": batch}, **auth, timeout=180)
        if r.status_code not in (200, 201):
            log.error("Batch %d failed: %s %s", i // args.batch_size + 1, r.status_code, r.text[:500])
            r.raise_for_status()
        body = r.json()
        c = int(body.get("created") or 0)
        f = int(body.get("failed") or 0)
        created += c
        failed += f
        log.info(
            "Batch %d/%d size=%d created=%d failed=%d elapsed=%.0fms",
            i // args.batch_size + 1,
            total_batches,
            len(batch),
            c,
            f,
            (time.monotonic() - t0) * 1000,
        )

    log.info("Done. total_created=%d total_failed=%d", created, failed)
    return 0 if failed == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
