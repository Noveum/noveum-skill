"""Shared helpers for noveum-dataset skill scripts."""

from __future__ import annotations

import os
import sys
from pathlib import Path
from typing import Any


def resolve_api_key(
    cli_key: str | None,
    env_key_name: str | None,
    env_file: Path | None,
) -> str:
    """Resolve API key from (in order): CLI flag, named env var, NOVEUM_API_KEY,
    first ``*_NOVEUM_API_KEY`` found in .env."""
    if env_file is not None and env_file.is_file():
        from dotenv import load_dotenv

        load_dotenv(env_file)
    else:
        cwd_env = Path.cwd() / ".env"
        if cwd_env.is_file():
            from dotenv import load_dotenv

            load_dotenv(cwd_env)

    if cli_key:
        return cli_key.strip()
    if env_key_name:
        v = os.getenv(env_key_name)
        if v:
            return v.strip()
    if os.getenv("NOVEUM_API_KEY"):
        return os.environ["NOVEUM_API_KEY"].strip()
    for k, v in os.environ.items():
        if k.endswith("_NOVEUM_API_KEY") and v:
            return v.strip()
    print(
        "ERROR: no Noveum API key found. Pass --api-key, set NOVEUM_API_KEY, "
        "or put *_NOVEUM_API_KEY in .env.",
        file=sys.stderr,
    )
    sys.exit(2)


def auth_kwargs(key: str) -> dict[str, Any]:
    """requests kwargs that match the platform's curl examples:
       Authorization Bearer header AND apiKeyCookie cookie."""
    return {
        "headers": {
            "Authorization": f"Bearer {key}",
            "Content-Type": "application/json",
        },
        "cookies": {"apiKeyCookie": key},
    }
