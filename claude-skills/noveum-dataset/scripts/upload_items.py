#!/usr/bin/env python3
"""Upload dataset items to Noveum. Creates the dataset if missing, batches
items, optionally publishes. scorer_results are NOT carried by this endpoint
— use upload_scorer_results.py for those.
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

# Top-level item fields that go inside `content` (per API schema).
CONTENT_FIELDS: tuple[str, ...] = (
    "agent_name",
    "agent_role",
    "agent_task",
    "agent_response",
    "system_prompt",
    "user_id",
    "session_id",
    "turn_id",
    "ground_truth",
    "expected_tool_call",
    "tools_available",
    "tool_calls",
    "tool_call_results",
    "parameters_passed",
    "retrieval_query",
    "retrieved_context",
    "exit_status",
    "agent_exit",
    "conversation_id",
    "speaker",
    "message",
    "conversation_context",
    "input_text",
    "output_text",
    "expected_output",
    "evaluation_context",
    "criteria",
    "quality_score",
    "validation_status",
    "validation_errors",
    "tags",
    "custom_attributes",
    "stt_data",
    "tts_data",
    "raw_complete_audio",
    "vad_metrics",
    "stt_metrics",
    "tts_metrics",
    "llm_metrics",
    "eou_metrics",
    "latency",
)

DEFAULTS_FOR_NULL: dict[str, Any] = {
    "tools_available": [],
    "tool_calls": [],
    "tool_call_results": [],
    "parameters_passed": {},
    "retrieval_query": [],
    "retrieved_context": [],
    "conversation_context": {},
    "evaluation_context": {},
    "validation_errors": [],
    "tags": [],
    "custom_attributes": {},
    "stt_data": [],
    "tts_data": {},
    "raw_complete_audio": {},
    "vad_metrics": [],
    "stt_metrics": [],
    "tts_metrics": [],
    "llm_metrics": [],
    "eou_metrics": [],
    "latency": {},
    "quality_score": 1,
}

ARRAY_FIELDS = {
    "tools_available",
    "tool_calls",
    "tool_call_results",
    "retrieval_query",
    "retrieved_context",
    "validation_errors",
    "tags",
    "stt_data",
    "vad_metrics",
    "stt_metrics",
    "tts_metrics",
    "llm_metrics",
    "eou_metrics",
}


def _parse_maybe_json(v: Any) -> Any:
    if not isinstance(v, str):
        return v
    s = v.strip()
    if not s:
        return None
    if s[0] not in "{[\"" and not s[0].isdigit():
        return v
    try:
        return json.loads(s)
    except (json.JSONDecodeError, ValueError):
        return v


def _scorer_results_to_dict(scorer_results: list[dict] | None) -> dict[str, Any]:
    out: dict[str, Any] = {}
    for sr in scorer_results or []:
        name = sr.get("scorer_name") or sr.get("scorer_id")
        if not name:
            continue
        md = _parse_maybe_json(sr.get("metadata"))
        out[name] = {
            "score": sr.get("score"),
            "passed": sr.get("passed"),
            "reasoning": sr.get("reasoning"),
            "metadata": md if md is not None else {},
            "scorer_id": sr.get("scorer_id"),
        }
    return out


def build_api_item(raw: dict) -> dict:
    content: dict[str, Any] = {}
    for k in CONTENT_FIELDS:
        if k in raw:
            v = _parse_maybe_json(raw[k])
            if v is None:
                v = DEFAULTS_FOR_NULL.get(k, "")
            elif k in ARRAY_FIELDS and isinstance(v, dict):
                v = [v]
            elif k in ARRAY_FIELDS and not isinstance(v, list):
                v = [v] if v else []
            content[k] = v
    # score_results echoed inside content for parity with the docs schema;
    # the API also stores scorer_results via the separate endpoint.
    content["score_results"] = _scorer_results_to_dict(raw.get("scorer_results"))

    metadata = _parse_maybe_json(raw.get("metadata")) or {}
    item: dict[str, Any] = {
        "item_id": raw.get("item_id"),
        "item_type": raw.get("item_type") or "agent",
        "content": content,
        "metadata": metadata if isinstance(metadata, dict) else {},
    }
    if raw.get("source_trace_id"):
        item["trace_id"] = raw["source_trace_id"]
    if raw.get("source_span_id"):
        item["span_id"] = raw["source_span_id"]
    return item


def get_dataset(slug: str, auth: dict, log: logging.Logger) -> dict | None:
    r = requests.get(f"{BASE_URL}/api/v1/datasets/{slug}", **auth, timeout=30)
    if r.status_code == 200:
        body = r.json()
        return body.get("dataset", body) if isinstance(body, dict) else body
    if r.status_code == 404:
        return None
    log.error("GET dataset: %s %s", r.status_code, r.text[:300])
    r.raise_for_status()
    return None


def create_dataset(slug: str, args, auth: dict, log: logging.Logger) -> dict:
    payload: dict[str, Any] = {
        "name": args.name or slug,
        "slug": slug,
        "description": args.description or "",
        "visibility": args.visibility,
        "dataset_type": args.dataset_type,
        "custom_attributes": {},
    }
    if args.project_id:
        payload["project_id"] = args.project_id
    if args.environment:
        payload["environment"] = args.environment
    if args.tags:
        payload["tags"] = args.tags
    r = requests.post(f"{BASE_URL}/api/v1/datasets", json=payload, **auth, timeout=60)
    if r.status_code not in (200, 201):
        log.error("Create dataset: %s %s", r.status_code, r.text[:500])
        r.raise_for_status()
    log.info("Created dataset slug=%s", slug)
    return r.json()


def push_items(
    slug: str, items: list[dict], batch_size: int, auth: dict, log: logging.Logger
) -> int:
    url = f"{BASE_URL}/api/v1/datasets/{slug}/items"
    pushed = 0
    for i in range(0, len(items), batch_size):
        batch = items[i : i + batch_size]
        t0 = time.monotonic()
        r = requests.post(url, json={"items": batch}, **auth, timeout=180)
        if r.status_code not in (200, 201):
            log.error("Batch %d-%d: %s %s", i, i + len(batch), r.status_code, r.text[:500])
            r.raise_for_status()
        pushed += len(batch)
        log.info(
            "Pushed %d/%d (last batch %d in %.0fms)",
            pushed,
            len(items),
            len(batch),
            (time.monotonic() - t0) * 1000,
        )
    return pushed


def publish(slug: str, version: str | None, auth: dict, log: logging.Logger) -> dict:
    payload = {"version": version} if version else {}
    r = requests.post(
        f"{BASE_URL}/api/v1/datasets/{slug}/versions/publish",
        json=payload,
        **auth,
        timeout=60,
    )
    if r.status_code not in (200, 201):
        log.error("Publish: %s %s", r.status_code, r.text[:500])
        r.raise_for_status()
    info = r.json()
    log.info("Published %s: %s", slug, info)
    return info


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", type=Path, required=True)
    parser.add_argument("--slug", required=True)
    parser.add_argument("--name", default=None)
    parser.add_argument("--description", default="")
    parser.add_argument(
        "--dataset-type",
        default="agent",
        choices=("agent", "conversational", "g-eval", "custom"),
    )
    parser.add_argument("--visibility", default="org", choices=("public", "org", "private"))
    parser.add_argument("--project-id", default=None)
    parser.add_argument("--environment", default=None)
    parser.add_argument("--tags", nargs="*", default=None)
    parser.add_argument("--batch-size", type=int, default=50)
    parser.add_argument("--publish", action="store_true")
    parser.add_argument("--publish-version", default=None)
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
    log = logging.getLogger("upload_items")

    raw_items = json.loads(args.input.read_text(encoding="utf-8"))
    log.info("Loaded %d items from %s", len(raw_items), args.input)
    api_items = [build_api_item(it) for it in raw_items]

    if args.dry_run:
        print(json.dumps(api_items[0] if api_items else {}, indent=2, default=str)[:4000])
        return 0

    key = resolve_api_key(args.api_key, args.env_key, args.env_file)
    auth = auth_kwargs(key)

    if get_dataset(args.slug, auth, log):
        log.info("Dataset %s exists; skipping create", args.slug)
    else:
        create_dataset(args.slug, args, auth, log)

    push_items(args.slug, api_items, args.batch_size, auth, log)

    if args.publish:
        publish(args.slug, args.publish_version, auth, log)

    log.info("Done.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
