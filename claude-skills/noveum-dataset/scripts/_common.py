"""Shared helpers for noveum-dataset skill scripts."""

from __future__ import annotations

import os
import sys
from pathlib import Path
from typing import Any, NoReturn

import requests


def _missing_key(message: str) -> NoReturn:
    print(f"ERROR: {message}", file=sys.stderr)
    sys.exit(2)


def resolve_api_key(
    cli_key: str | None,
    env_key_name: str | None,
    env_file: Path | None,
) -> str:
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
        selected = os.getenv(env_key_name, "").strip()
        if selected:
            return selected
        _missing_key(f"{env_key_name} is not set; refusing to fall back to another key.")
    default_key = os.getenv("NOVEUM_API_KEY", "").strip()
    if default_key:
        return default_key
    scoped = sorted(
        k for k, v in os.environ.items() if k.endswith("_NOVEUM_API_KEY") and v.strip()
    )
    if len(scoped) == 1:
        return os.environ[scoped[0]].strip()
    if scoped:
        _missing_key(
            f"several project keys found ({', '.join(scoped)}); pick one with --env-key."
        )
    _missing_key(
        "no Noveum API key found. Pass --api-key, set NOVEUM_API_KEY, "
        "or put one *_NOVEUM_API_KEY in .env."
    )


def _refuse_redirect(response: requests.Response, *args: Any, **kwargs: Any) -> None:
    if 300 <= response.status_code < 400:
        response.close()
        raise requests.HTTPError(
            f"refused redirect {response.status_code} from {response.url} "
            f"to {response.headers.get('Location')}; the API key is only sent to "
            "NOVEUM_BASE_URL",
            response=response,
        )


def auth_kwargs(key: str) -> dict[str, Any]:
    return {
        "headers": {
            "Authorization": f"Bearer {key}",
            "Content-Type": "application/json",
        },
        "allow_redirects": False,
        "hooks": {"response": _refuse_redirect},
    }
