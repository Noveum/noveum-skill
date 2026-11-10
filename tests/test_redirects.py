import os
import subprocess
import sys
import urllib.error
import urllib.request

import pytest
import requests

from conftest import ROOT, load_script

STDLIB_SCRIPTS = [
    "noveum-ai/scripts/fetch_to_file.py",
    "noveum-ai/scripts/check_integration.py",
    "noveum-ai/scripts/send_test_trace.py",
]


@pytest.mark.parametrize("script", STDLIB_SCRIPTS)
def test_stdlib_helpers_refuse_redirects_and_never_forward_the_key(script, redirect_pair):
    origin, target = redirect_pair
    module = load_script(script, script.replace("/", "_").replace(".py", ""))
    request = urllib.request.Request(
        f"{origin.url}/v1/projects", headers={"Authorization": "Bearer secret-key"}
    )

    with pytest.raises(urllib.error.HTTPError) as refused:
        module.OPENER.open(request, timeout=5)

    assert refused.value.code == 302
    assert origin.requests[0]["authorization"] == "Bearer secret-key"
    assert target.requests == []


def test_fetch_to_file_exits_with_an_error_on_a_redirect(redirect_pair, tmp_path):
    origin, target = redirect_pair
    result = subprocess.run(
        [
            sys.executable,
            str(ROOT / "noveum-ai/scripts/fetch_to_file.py"),
            "/v1/projects",
            "--out",
            str(tmp_path / "out.json"),
        ],
        env={**os.environ, "NOVEUM_API_KEY": "secret-key", "NOVEUM_ENDPOINT": origin.url},
        capture_output=True,
        text=True,
        timeout=30,
    )

    assert result.returncode == 2
    assert target.requests == []


def test_dataset_helpers_refuse_redirects_and_keep_the_key_off_other_hosts(redirect_pair):
    origin, target = redirect_pair
    common = load_script("claude-skills/noveum-dataset/scripts/_common.py", "_common")

    with pytest.raises(requests.HTTPError, match="refused redirect 302"):
        requests.get(f"{origin.url}/api/v1/datasets", timeout=5, **common.auth_kwargs("secret-key"))

    assert origin.requests[0]["authorization"] == "Bearer secret-key"
    assert target.requests == []


def test_dataset_helpers_send_the_key_only_as_a_bearer_header():
    common = load_script("claude-skills/noveum-dataset/scripts/_common.py", "_common")

    kwargs = common.auth_kwargs("secret-key")

    assert kwargs["headers"]["Authorization"] == "Bearer secret-key"
    assert "cookies" not in kwargs
    assert kwargs["allow_redirects"] is False


def test_a_named_key_variable_that_is_unset_never_falls_back(monkeypatch, tmp_path):
    common = load_script("claude-skills/noveum-dataset/scripts/_common.py", "_common")
    monkeypatch.chdir(tmp_path)
    monkeypatch.delenv("SHOP_NOVEUM_API_KEY", raising=False)
    monkeypatch.setenv("NOVEUM_API_KEY", "default-key")

    with pytest.raises(SystemExit) as exited:
        common.resolve_api_key(None, "SHOP_NOVEUM_API_KEY", None)

    assert exited.value.code == 2


def test_several_project_keys_are_never_guessed_between(monkeypatch, tmp_path):
    common = load_script("claude-skills/noveum-dataset/scripts/_common.py", "_common")
    monkeypatch.chdir(tmp_path)
    monkeypatch.delenv("NOVEUM_API_KEY", raising=False)
    monkeypatch.setenv("SHOP_NOVEUM_API_KEY", "shop-key")
    monkeypatch.setenv("BILLING_NOVEUM_API_KEY", "billing-key")

    with pytest.raises(SystemExit) as exited:
        common.resolve_api_key(None, None, None)

    assert exited.value.code == 2
