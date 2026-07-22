#!/usr/bin/env python3
"""Run the Hub release finalizer with a bounded Dataset Viewer materialization wait.

The underlying release controller remains fail-closed. This entrypoint changes only
one transport boundary: Hugging Face Dataset Viewer may briefly return 429/5xx or
an explicit busy/not-ready payload after a verified dataset publication. Those
transient states are retried with bounded backoff; every other response is returned
to the controller unchanged, and final success still requires its exact HTTP 200,
JSON-object, no-error contract.
"""
from __future__ import annotations

import time
from typing import Any

import requests

import hf_release_finalization as finalizer

RETRYABLE_STATUS_CODES = frozenset({429, 500, 502, 503, 504})
TRANSIENT_ERROR_MARKERS = (
    "busy",
    "not ready",
    "retry",
    "processing",
    "loading",
)
DEFAULT_ATTEMPTS = 12

_ORIGINAL_GET = requests.get
_ACTIVE_FINALIZER: finalizer.Finalizer | None = None
_VIEWER_STATS: dict[str, Any] = {
    "attempts": 0,
    "transient_retries": 0,
    "last_transient": None,
}


def _response_error_text(response: requests.Response) -> str:
    """Return a bounded error description without weakening JSON validation."""
    try:
        payload = response.json()
    except ValueError:
        return response.text[:300]
    if isinstance(payload, dict):
        return str(payload.get("error") or payload)[:300]
    return str(payload)[:300]


def _is_transient_response(response: requests.Response) -> tuple[bool, str]:
    detail = f"HTTP {response.status_code}: {_response_error_text(response)}"
    if response.status_code in RETRYABLE_STATUS_CODES:
        return True, detail
    if response.status_code != 200:
        return False, detail
    try:
        payload = response.json()
    except ValueError:
        return False, detail
    if not isinstance(payload, dict) or not payload.get("error"):
        return False, detail
    error_text = str(payload.get("error") or "").lower()
    return any(marker in error_text for marker in TRANSIENT_ERROR_MARKERS), detail


def get_with_viewer_retry(
    url: str,
    *args: Any,
    attempts: int = DEFAULT_ATTEMPTS,
    **kwargs: Any,
) -> requests.Response:
    """Delegate ordinary GETs and retry only the exact Viewer materialization URL."""
    if url != finalizer.VIEWER_URL:
        return _ORIGINAL_GET(url, *args, **kwargs)
    if attempts < 1:
        raise ValueError("attempts must be positive")

    last_detail = "no response"
    for attempt in range(1, attempts + 1):
        _VIEWER_STATS["attempts"] = attempt
        try:
            response = _ORIGINAL_GET(url, *args, **kwargs)
        except requests.RequestException as exc:
            transient = True
            last_detail = f"{type(exc).__name__}: {exc}"
        else:
            transient, last_detail = _is_transient_response(response)
            if not transient:
                return response

        if attempt == attempts:
            raise RuntimeError(
                "Dataset Viewer contract did not converge after "
                f"{attempts} attempts: {last_detail}"
            )

        delay = min(15 * attempt, 60)
        _VIEWER_STATS["transient_retries"] = int(
            _VIEWER_STATS["transient_retries"]
        ) + 1
        _VIEWER_STATS["last_transient"] = last_detail
        if _ACTIVE_FINALIZER is not None:
            _ACTIVE_FINALIZER.record(
                finalizer.DATASET_ID,
                "dataset-viewer-wait",
                "warning",
                f"attempt={attempt}/{attempts}; retry_in={delay}s; {last_detail}",
            )
        else:
            print(
                "[   warning] dataset-viewer-wait: "
                f"attempt={attempt}/{attempts}; retry_in={delay}s; {last_detail}"
            )
        time.sleep(delay)

    raise AssertionError("unreachable")


_BaseFinalizer = finalizer.Finalizer


class RetryingFinalizer(_BaseFinalizer):
    """Expose retry evidence while preserving the original controller behavior."""

    def finalize_dataset(self) -> None:
        global _ACTIVE_FINALIZER
        _ACTIVE_FINALIZER = self
        try:
            super().finalize_dataset()
        finally:
            _ACTIVE_FINALIZER = None

    def report(self) -> dict[str, Any]:
        report = super().report()
        report["dataset_viewer_retry"] = dict(_VIEWER_STATS)
        return report


def main() -> int:
    requests.get = get_with_viewer_retry
    finalizer.requests.get = get_with_viewer_retry
    finalizer.Finalizer = RetryingFinalizer
    return finalizer.main()


if __name__ == "__main__":
    raise SystemExit(main())
