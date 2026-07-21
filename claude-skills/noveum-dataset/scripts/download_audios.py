#!/usr/bin/env python3
"""Download audio files from Noveum by audio_uuid.

Either pass UUIDs directly via --uuids, or point --input at a dataset JSON
(from download_items.py or any export) and the script will harvest every
audio_uuid it can find inside stt_data/tts_data/raw_complete_audio.

Equivalent to:
  curl https://noveum.ai/api/v1/audio/{audio_uuid} \\
       -H 'Authorization: Bearer $KEY' --cookie 'apiKeyCookie=$KEY' > out.wav
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
from typing import Any

import requests

sys.path.insert(0, str(Path(__file__).resolve().parent))
from _common import auth_kwargs, resolve_api_key  # noqa: E402

BASE_URL = os.getenv("NOVEUM_BASE_URL", "https://noveum.ai")
MAX_RETRIES = 3
TIMEOUT_S = 120
EXTS_BY_CT = {
    "audio/wav": ".wav",
    "audio/x-wav": ".wav",
    "audio/ogg": ".ogg",
    "audio/mpeg": ".mp3",
    "audio/mp4": ".m4a",
    "audio/aac": ".aac",
    "audio/flac": ".flac",
    "audio/webm": ".webm",
}


def _parse_maybe_json(v: Any) -> Any:
    if isinstance(v, str) and v.strip().startswith(("{", "[")):
        try:
            return json.loads(v)
        except (json.JSONDecodeError, ValueError):
            return v
    return v


def harvest_audio_uuids(items: list[dict]) -> list[str]:
    """Walk items and pull every audio_uuid we can find (de-duplicated, order
    preserved). Looks in stt_data, tts_data, raw_complete_audio."""
    seen: dict[str, None] = {}
    for it in items:
        for key in ("stt_data", "tts_data", "raw_complete_audio"):
            v = _parse_maybe_json(it.get(key))
            for entry in v if isinstance(v, list) else [v]:
                if isinstance(entry, dict):
                    u = entry.get("audio_uuid")
                    if isinstance(u, str) and u:
                        seen.setdefault(u, None)
    return list(seen.keys())


def download_one(
    uuid: str, out_dir: Path, auth: dict, log: logging.Logger, overwrite: bool
) -> tuple[str, str | None]:
    """Return (uuid, error_str_or_None)."""
    out_dir.mkdir(parents=True, exist_ok=True)
    candidates = [out_dir / f"{uuid}{ext}" for ext in (".wav", ".ogg", ".mp3", "")]
    if not overwrite:
        for c in candidates:
            if c.is_file() and c.stat().st_size > 0:
                return uuid, None  # cached

    url = f"{BASE_URL}/api/v1/audio/{uuid}"
    last_err: str | None = None
    for attempt in range(MAX_RETRIES):
        try:
            r = requests.get(url, timeout=TIMEOUT_S, stream=True, **auth)
            if r.status_code == 200:
                ext = EXTS_BY_CT.get(
                    (r.headers.get("Content-Type") or "").split(";")[0].strip(),
                    ".wav",
                )
                tmp = out_dir / f"{uuid}{ext}.part"
                with tmp.open("wb") as f:
                    for chunk in r.iter_content(chunk_size=64 * 1024):
                        if chunk:
                            f.write(chunk)
                final = out_dir / f"{uuid}{ext}"
                os.replace(tmp, final)
                return uuid, None
            if r.status_code in (429,) or r.status_code >= 500:
                last_err = f"{r.status_code}"
                time.sleep(2.0 * (attempt + 1))
                continue
            return uuid, f"HTTP {r.status_code}: {r.text[:200]}"
        except Exception as e:
            last_err = str(e)
            time.sleep(2.0 * (attempt + 1))
    return uuid, last_err or "unknown"


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--input",
        type=Path,
        default=None,
        help="Dataset JSON to harvest audio_uuids from.",
    )
    parser.add_argument(
        "--uuids",
        nargs="*",
        default=None,
        help="Explicit list of audio_uuids (alternative to --input).",
    )
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--workers", type=int, default=10)
    parser.add_argument(
        "--overwrite",
        action="store_true",
        help="Re-download even if file already exists.",
    )
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
    log = logging.getLogger("download_audios")

    if args.uuids:
        uuids = list(args.uuids)
    elif args.input:
        items = json.loads(args.input.read_text(encoding="utf-8"))
        uuids = harvest_audio_uuids(items)
        log.info("Harvested %d unique audio_uuids from %s", len(uuids), args.input)
    else:
        log.error("Pass either --uuids or --input.")
        return 2

    if not uuids:
        log.warning("No UUIDs to download.")
        return 0

    key = resolve_api_key(args.api_key, args.env_key, args.env_file)
    auth = auth_kwargs(key)

    done = failed = 0
    with ThreadPoolExecutor(max_workers=args.workers) as ex:
        futs = {
            ex.submit(download_one, u, args.output_dir, auth, log, args.overwrite): u
            for u in uuids
        }
        for fut in as_completed(futs):
            u = futs[fut]
            _, err = fut.result()
            if err:
                failed += 1
                log.warning("Fail %s: %s", u, err)
            else:
                done += 1
            total = done + failed
            if total % 25 == 0 or total == len(uuids):
                log.info("%d/%d (%d failed)", total, len(uuids), failed)

    log.info("Done. ok=%d failed=%d → %s", done, failed, args.output_dir)
    return 0 if failed == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
