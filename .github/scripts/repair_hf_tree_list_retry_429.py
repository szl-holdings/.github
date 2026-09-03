#!/usr/bin/env python3
"""Install a bounded HTTP-429 retry around the HF tree-list preflight read."""
from __future__ import annotations

import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
DEPLOYER = ROOT / ".github" / "scripts" / "hf_deploy_from_dockerfile.py"
TESTS = ROOT / ".github" / "scripts" / "test_hf_deploy_from_dockerfile.py"


def replace_exact(path: Path, old: str, new: str) -> None:
    text = path.read_text(encoding="utf-8")
    count = text.count(old)
    if count != 1:
        raise SystemExit(f"{path}: expected one replacement target, found {count}")
    path.write_text(text.replace(old, new, 1), encoding="utf-8")


def main() -> int:
    constants_anchor = '''HF_HOST = "https://huggingface.co"
UA = {"User-Agent": "hf-deploy-from-dockerfile/1.0"}
TERMINAL_RUNTIME_STAGES = {"BUILD_ERROR", "CONFIG_ERROR", "RUNTIME_ERROR"}
RESERVED_HF_ROOT_TARGETS = {"dockerfile", "dockerfile.dockerignore"}
'''
    constants_replacement = '''HF_HOST = "https://huggingface.co"
UA = {"User-Agent": "hf-deploy-from-dockerfile/1.0"}
TERMINAL_RUNTIME_STAGES = {"BUILD_ERROR", "CONFIG_ERROR", "RUNTIME_ERROR"}
RESERVED_HF_ROOT_TARGETS = {"dockerfile", "dockerfile.dockerignore"}
HF_TREE_LIST_MAX_ATTEMPTS = 5
HF_TREE_LIST_BASE_DELAY_S = 2.0
HF_TREE_LIST_MAX_DELAY_S = 30.0
'''

    helper_anchor = '''    return operations


def fetch_github_json(url, token):
'''
    helper_replacement = '''    return operations


def _http_status_from_exception(exc):
    """Extract an HTTP status from requests-, urllib-, or SDK-style errors."""
    response = getattr(exc, "response", None)
    status = getattr(response, "status_code", None)
    if status is None:
        status = getattr(exc, "status_code", None)
    if status is None:
        status = getattr(exc, "code", None)
    try:
        return int(status)
    except (TypeError, ValueError):
        return None


def _retry_after_seconds(exc):
    """Return a non-negative numeric Retry-After hint, or zero when absent."""
    response = getattr(exc, "response", None)
    headers = getattr(response, "headers", None) or {}
    raw = headers.get("Retry-After") or headers.get("retry-after")
    try:
        return max(0.0, float(raw))
    except (TypeError, ValueError):
        return 0.0


def list_repo_files_with_rate_limit_retry(
        api, *, repo_id, repo_type, max_attempts=HF_TREE_LIST_MAX_ATTEMPTS):
    """Retry only the idempotent HF tree-list read on HTTP 429.

    Uploads, commits, deletes, source binding, and restart calls are intentionally
    outside this helper. Non-429 failures propagate immediately. Exhaustion
    propagates the final SDK exception so the deployment remains fail-closed.
    """
    try:
        attempts = int(max_attempts)
    except (TypeError, ValueError) as exc:
        raise DeployContractError("HF tree-list retry attempts must be an integer") from exc
    if not 1 <= attempts <= 10:
        raise DeployContractError("HF tree-list retry attempts must be between 1 and 10")

    for attempt in range(1, attempts + 1):
        try:
            return api.list_repo_files(repo_id=repo_id, repo_type=repo_type)
        except Exception as exc:  # noqa: BLE001 - SDK error type is lazy-imported
            if _http_status_from_exception(exc) != 429 or attempt >= attempts:
                raise
            backoff = min(
                HF_TREE_LIST_MAX_DELAY_S,
                HF_TREE_LIST_BASE_DELAY_S * (2 ** (attempt - 1)),
            )
            server_hint = min(
                HF_TREE_LIST_MAX_DELAY_S,
                _retry_after_seconds(exc),
            )
            delay = max(backoff, server_hint)
            print(
                "::warning::HF tree listing rate-limited (HTTP 429); "
                f"retry {attempt + 1}/{attempts} in {delay:.1f}s"
            )
            time.sleep(delay)
    raise AssertionError("bounded HF tree-list retry loop exited unexpectedly")


def fetch_github_json(url, token):
'''

    call_anchor = '''        live = api.list_repo_files(repo_id=args.hf_repo, repo_type="space")
'''
    call_replacement = '''        live = list_repo_files_with_rate_limit_retry(
            api,
            repo_id=args.hf_repo,
            repo_type="space",
        )
'''

    test_anchor = '''class TestContentIdentity(unittest.TestCase):
'''
    test_replacement = '''class TestHuggingFaceTreeListRetry(unittest.TestCase):
    @staticmethod
    def _error(status, retry_after=None):
        error = RuntimeError(f"HTTP {status}")
        headers = {}
        if retry_after is not None:
            headers["Retry-After"] = retry_after
        error.response = types.SimpleNamespace(
            status_code=status,
            headers=headers,
        )
        return error

    def test_retries_rate_limited_read_and_honors_server_hint(self):
        api = mock.Mock()
        api.list_repo_files.side_effect = [
            self._error(429, "7"),
            ["README.md", "app.py"],
        ]
        with mock.patch.object(dep.time, "sleep") as sleep:
            files = dep.list_repo_files_with_rate_limit_retry(
                api,
                repo_id="SZLHOLDINGS/a11oy",
                repo_type="space",
            )
        self.assertEqual(files, ["README.md", "app.py"])
        self.assertEqual(api.list_repo_files.call_count, 2)
        sleep.assert_called_once_with(7.0)

    def test_non_429_propagates_without_retry_or_sleep(self):
        api = mock.Mock()
        error = self._error(503)
        api.list_repo_files.side_effect = error
        with mock.patch.object(dep.time, "sleep") as sleep:
            with self.assertRaisesRegex(RuntimeError, "HTTP 503"):
                dep.list_repo_files_with_rate_limit_retry(
                    api,
                    repo_id="SZLHOLDINGS/a11oy",
                    repo_type="space",
                )
        api.list_repo_files.assert_called_once_with(
            repo_id="SZLHOLDINGS/a11oy",
            repo_type="space",
        )
        sleep.assert_not_called()

    def test_429_exhaustion_is_bounded_and_fail_closed(self):
        api = mock.Mock()
        api.list_repo_files.side_effect = [self._error(429) for _ in range(5)]
        with mock.patch.object(dep.time, "sleep") as sleep:
            with self.assertRaisesRegex(RuntimeError, "HTTP 429"):
                dep.list_repo_files_with_rate_limit_retry(
                    api,
                    repo_id="SZLHOLDINGS/a11oy",
                    repo_type="space",
                )
        self.assertEqual(api.list_repo_files.call_count, 5)
        self.assertEqual(
            [call.args[0] for call in sleep.call_args_list],
            [2.0, 4.0, 8.0, 16.0],
        )

    def test_retry_count_is_strictly_bounded(self):
        api = mock.Mock()
        for value in (0, 11, "not-an-integer"):
            with self.subTest(value=value), self.assertRaises(
                dep.DeployContractError
            ):
                dep.list_repo_files_with_rate_limit_retry(
                    api,
                    repo_id="SZLHOLDINGS/a11oy",
                    repo_type="space",
                    max_attempts=value,
                )
        api.list_repo_files.assert_not_called()


class TestContentIdentity(unittest.TestCase):
'''

    replace_exact(DEPLOYER, constants_anchor, constants_replacement)
    replace_exact(DEPLOYER, helper_anchor, helper_replacement)
    replace_exact(DEPLOYER, call_anchor, call_replacement)
    replace_exact(TESTS, test_anchor, test_replacement)

    commands = [
        ["python3", "-m", "py_compile", str(DEPLOYER), str(TESTS)],
        ["python3", str(TESTS)],
        ["git", "diff", "--check"],
    ]
    for command in commands:
        subprocess.run(command, cwd=ROOT, check=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
