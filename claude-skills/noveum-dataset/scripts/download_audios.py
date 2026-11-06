#!/usr/bin/env python3
"""Download audio files from Noveum by audio_uuid.

Either pass UUIDs directly via --uuids, or point --input at a dataset JSON
(from download_items.py or any export) and the script will harvest every
audio_uuid it can find inside stt_data/tts_data/raw_complete_audio.

Equivalent to:
  curl https://noveum.ai/api/v1/audio/{audio_uuid}/serve \\
       -H 'Authorization: Bearer $KEY' > out.wav
"""

from __future__ import annotations

import argparse
import json
import logging
import os
import sys
import tempfile
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
AUDIO_EXTS = (".wav", ".mp3", ".ogg", ".flac", ".m4a", ".webm", ".aac")
SNIFF_BYTES = 16


def sniff_audio_ext(head: bytes) -> str | None:
    if head[:4] == b"RIFF" and head[8:12] == b"WAVE":
        return ".wav"
    if head[:3] == b"ID3":
        return ".mp3"
    if head[:4] == b"OggS":
        return ".ogg"
    if head[:4] == b"fLaC":
        return ".flac"
    if head[4:8] == b"ftyp":
        return ".m4a"
    if head[:4] == b"\x1a\x45\xdf\xa3":
        return ".webm"
    if len(head) > 1 and head[0] == 0xFF and head[1] & 0xF6 == 0xF0:
        return ".aac"
    if len(head) > 1 and head[0] == 0xFF and head[1] & 0xE0 == 0xE0:
        return ".mp3"
    return None


def is_cached_audio(path: Path) -> bool:
    if not path.is_file():
        return False
    with path.open("rb") as f:
        return sniff_audio_ext(f.read(SNIFF_BYTES)) == path.suffix


class TruncatedDownload(Exception):
    pass


def save_audio(r: requests.Response, out_dir: Path, uuid: str) -> str | None:
    fd, tmp_name = tempfile.mkstemp(dir=out_dir, prefix=f".{uuid}.", suffix=".part")
    tmp = Path(tmp_name)
    try:
        head = b""
        total = 0
        with os.fdopen(fd, "wb") as f:
            for chunk in r.iter_content(chunk_size=64 * 1024):
                if chunk:
                    if len(head) < SNIFF_BYTES:
                        head += chunk[: SNIFF_BYTES - len(head)]
                    f.write(chunk)
                    total += len(chunk)
        declared = r.headers.get("Content-Length")
        if not r.headers.get("Content-Encoding") and declared and declared.isdigit():
            if total != int(declared):
                raise TruncatedDownload(f"got {total} of {declared} bytes")
        ext = sniff_audio_ext(head)
        if ext is None:
            content_type = r.headers.get("Content-Type") or "unknown"
            return f"response is not audio (Content-Type {content_type}, {total} bytes)"
        os.replace(tmp, out_dir / f"{uuid}{ext}")
        return None
    finally:
        tmp.unlink(missing_ok=True)


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
    out_dir.mkdir(parents=True, exist_ok=True)
    if not overwrite:
        for ext in AUDIO_EXTS:
            if is_cached_audio(out_dir / f"{uuid}{ext}"):
                return uuid, None

    url = f"{BASE_URL}/api/v1/audio/{uuid}/serve"
    last_err: str | None = None
    for attempt in range(MAX_RETRIES):
        try:
            with requests.get(url, timeout=TIMEOUT_S, stream=True, **auth) as r:
                if r.status_code == 200:
                    return uuid, save_audio(r, out_dir, uuid)
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
