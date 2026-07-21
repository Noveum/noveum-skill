#!/usr/bin/env python3
"""Download every item of a Noveum dataset to a single JSON file.

Equivalent to:
  curl https://noveum.ai/api/v1/datasets/{slug}/items/ids   (list ids)
  curl https://noveum.ai/api/v1/datasets/{slug}/items/{id}  (per item, parallel)
"""

from __future__ import annotations

import argparse
import json
import logging
import os
import sys
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

import requests

sys.path.insert(0, str(Path(__file__).resolve().parent))
from _common import auth_kwargs, resolve_api_key  # noqa: E402

BASE_URL = os.getenv("NOVEUM_BASE_URL", "https://noveum.ai")
MAX_RETRIES = 3
RETRY_DELAY_S = 2.0
IDS_TIMEOUT_S = 300
ITEM_TIMEOUT_S = 60


def _get_with_retry(url: str, auth: dict, timeout: int, log: logging.Logger) -> dict:
    last_exc: Exception | None = None
    for attempt in range(MAX_RETRIES):
        try:
            r = requests.get(url, timeout=timeout, **auth)
            if r.status_code == 200:
                return r.json()
            if r.status_code in (429,) or r.status_code >= 500:
                last_exc = RuntimeError(f"{r.status_code}: {r.text[:200]}")
                time.sleep(RETRY_DELAY_S * (attempt + 1))
                continue
            r.raise_for_status()
        except Exception as e:
            last_exc = e
            log.warning("GET %s attempt %d/%d: %s", url, attempt + 1, MAX_RETRIES, e)
            time.sleep(RETRY_DELAY_S * (attempt + 1))
    raise RuntimeError(f"exhausted retries for {url}: {last_exc}")


def fetch_ids(slug: str, auth: dict, log: logging.Logger) -> list[str]:
    url = f"{BASE_URL}/api/v1/datasets/{slug}/items/ids"
    data = _get_with_retry(url, auth, IDS_TIMEOUT_S, log)
    ids = data.get("items") or []
    if ids and isinstance(ids[0], dict):
        ids = [str(it.get("item_id") or it.get("id")) for it in ids if it]
    log.info("Found %d item ids for slug=%s", len(ids), slug)
    return [str(i) for i in ids if i]


def fetch_item(slug: str, item_id: str, auth: dict, log: logging.Logger) -> dict | None:
    url = f"{BASE_URL}/api/v1/datasets/{slug}/items/{item_id}"
    try:
        data = _get_with_retry(url, auth, ITEM_TIMEOUT_S, log)
    except RuntimeError as e:
        log.error("Drop item %s: %s", item_id, e)
        return None
    return data.get("item") or data


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--slug", required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--workers", type=int, default=10)
    parser.add_argument("--api-key", default=None)
    parser.add_argument("--env-key", default=None, help="Env var name holding the API key.")
    parser.add_argument("--env-file", type=Path, default=None)
    args = parser.parse_args()

    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s - %(levelname)s - %(message)s",
        datefmt="%H:%M:%S",
        stream=sys.stderr,
        force=True,
    )
    log = logging.getLogger("download_items")

    key = resolve_api_key(args.api_key, args.env_key, args.env_file)
    auth = auth_kwargs(key)

    ids = fetch_ids(args.slug, auth, log)
    if not ids:
        log.error("No item ids returned for %s", args.slug)
        return 1

    items: list[dict | None] = [None] * len(ids)
    done = err = 0
    with ThreadPoolExecutor(max_workers=args.workers) as ex:
        fut_idx = {
            ex.submit(fetch_item, args.slug, iid, auth, log): i
            for i, iid in enumerate(ids)
        }
        for fut in as_completed(fut_idx):
            i = fut_idx[fut]
            res = fut.result()
            if res is None:
                err += 1
            else:
                items[i] = res
                done += 1
            total = done + err
            if total % 50 == 0 or total == len(ids):
                log.info("%d/%d (%d errors)", total, len(ids), err)

    final = [it for it in items if it is not None]
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(
        json.dumps(final, indent=2, ensure_ascii=False), encoding="utf-8"
    )
    log.info("Wrote %d items → %s (errors=%d)", len(final), args.output, err)
    return 0 if err == 0 else (1 if not final else 0)


if __name__ == "__main__":
    raise SystemExit(main())
