#!/usr/bin/env python3
"""Fail-closed public model-evidence audit for the SZLHOLDINGS Hub estate.

The Hugging Face Models tab can contain checkpoints, adapters, GGUF files,
NumPy demonstrations, software kernels, documentation, and roadmap stubs. This
checker keeps those categories distinct and never turns repository visibility,
a README claim, or a self-authored receipt into a quality or runtime pass.

The live path is read-only. It resolves every public model repository to an
immutable Hub revision, inventories files, reads the root card at that exact
revision, and emits JSON plus a bounded Markdown summary. ``--enforce`` can
hold the scheduled workflow red for unsafe executable metadata, unqualified
frontier claims without structured results, or weighted artifacts without
Hub-standard evaluation metadata.

Exit codes:
  0 = collection completed and no enforced violation was found.
  1 = collection completed and at least one enforced violation was found.
  2 = collection could not be completed or its minimum coverage was not met.
"""
from __future__ import annotations

import argparse
import json
import os
import re
import sys
import urllib.error
import urllib.parse
import urllib.request
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path, PurePosixPath
from typing import Any, Iterable

HF_API = "https://huggingface.co/api"
HF_HOST = "https://huggingface.co"
DEFAULT_ORG = "SZLHOLDINGS"
SCHEMA = "szl.hf-model-evidence-audit/v1"
SHA40 = re.compile(r"^[0-9a-f]{40}$")

WEIGHT_SUFFIXES = (".safetensors", ".gguf", ".npz", ".onnx")
KNOWN_WEIGHT_NAMES = {
    "adapter_model.bin",
    "pytorch_model.bin",
    "tf_model.h5",
    "flax_model.msgpack",
}
UNSAFE_EXECUTABLE_SUFFIXES = (".pkl", ".pickle", ".joblib")
UNSAFE_EXECUTABLE_NAMES = {"training_args.bin"}
STRUCTURED_RESULT_FILES = {
    "eval_results.json",
    "model-index.yaml",
    "model-index.yml",
    "results.json",
}
OVERCLAIM = re.compile(
    r"(?i)(?:\bSOTA\b|state[- ]of[- ]the[- ]art|fully[- ]trained|"
    r"frontier[- ]class|best[- ]in[- ]class)"
)
NEGATING_QUALIFIER = re.compile(
    r"(?i)(?:\bno\b|\bnot\b|does not|do not|cannot|can't|unsupported|"
    r"unproven|not established|not claimed|no claim|roadmap|target only|"
    r"would require|without .* evidence)"
)


class AuditIncomplete(RuntimeError):
    """Raised when the remote inventory cannot be proved complete enough."""


def _token() -> str | None:
    for name in ("HF_ORG_TOKEN", "HF_TOKEN", "HF_WRITE_TOKEN"):
        value = os.environ.get(name)
        if value:
            return value
    return None


def _request(url: str, token: str | None) -> urllib.request.Request:
    request = urllib.request.Request(url)
    request.add_header("Accept", "application/json")
    request.add_header("User-Agent", "szl-hf-model-evidence-audit/1")
    if token:
        request.add_header("Authorization", "Bearer " + token)
    return request


def _get_json(url: str, token: str | None) -> Any:
    with urllib.request.urlopen(_request(url, token), timeout=45) as response:
        return json.load(response)


def _get_text(url: str, token: str | None) -> str | None:
    try:
        request = _request(url, token)
        request.headers["Accept"] = "text/plain"
        with urllib.request.urlopen(request, timeout=45) as response:
            return response.read().decode("utf-8", "replace")
    except urllib.error.HTTPError as error:
        if error.code == 404:
            return None
        raise


def _repo_id(item: dict[str, Any]) -> str:
    return str(item.get("id") or item.get("modelId") or "")


def _paths(info: dict[str, Any]) -> list[str]:
    paths = []
    for sibling in info.get("siblings") or []:
        if not isinstance(sibling, dict):
            continue
        path = sibling.get("rfilename") or sibling.get("path")
        if path:
            paths.append(str(path).replace("\\", "/"))
    return sorted(set(paths))


def weight_files(paths: Iterable[str]) -> list[str]:
    """Return loadable-looking weight artifacts, excluding trainer metadata."""
    result = []
    for path in paths:
        name = PurePosixPath(path).name.lower()
        if name in UNSAFE_EXECUTABLE_NAMES:
            continue
        if name in KNOWN_WEIGHT_NAMES or name.endswith(WEIGHT_SUFFIXES):
            result.append(path)
    return sorted(set(result))


def unsafe_executable_files(paths: Iterable[str]) -> list[str]:
    result = []
    for path in paths:
        name = PurePosixPath(path).name.lower()
        if name in UNSAFE_EXECUTABLE_NAMES or name.endswith(UNSAFE_EXECUTABLE_SUFFIXES):
            result.append(path)
    return sorted(set(result))


def structured_evaluation(info: dict[str, Any], paths: Iterable[str], readme: str) -> dict[str, Any]:
    card = info.get("cardData") or info.get("card_data") or {}
    if not isinstance(card, dict):
        card = {}
    card_keys = [
        key
        for key in ("model-index", "model_index", "eval_results")
        if card.get(key)
    ]
    result_files = [
        path
        for path in paths
        if PurePosixPath(path).name.lower() in STRUCTURED_RESULT_FILES
    ]
    readme_keys = sorted(
        set(
            match.group(1).lower()
            for match in re.finditer(
                r"(?m)^\s*(model-index|eval_results)\s*:",
                readme,
            )
        )
    )
    return {
        "present": bool(card_keys or result_files or readme_keys),
        "card_keys": card_keys,
        "files": sorted(result_files),
        "readme_keys": readme_keys,
    }


def unqualified_claims(readme: str) -> list[str]:
    """Return frontier phrases that are not locally bounded by a disclaimer."""
    claims = []
    normalized = re.sub(r"\s+", " ", readme)
    for match in OVERCLAIM.finditer(normalized):
        start = max(0, match.start() - 120)
        end = min(len(normalized), match.end() + 120)
        window = normalized[start:end]
        if NEGATING_QUALIFIER.search(window):
            continue
        claims.append(match.group(0))
    return sorted(set(claims), key=str.lower)


def _card_value(info: dict[str, Any], key: str) -> Any:
    card = info.get("cardData") or info.get("card_data") or {}
    if isinstance(card, dict) and card.get(key) not in (None, "", []):
        return card.get(key)
    return info.get(key)


def artifact_kind(info: dict[str, Any], weights: list[str]) -> str:
    library = str(info.get("library_name") or "").lower()
    lower = [path.lower() for path in weights]
    if not weights:
        return "software_kernel_or_non_weight_asset" if library == "kernels" else "no_loadable_weights"
    if any(path.endswith(".gguf") for path in lower):
        return "gguf_quantization"
    if any(path.endswith(".safetensors") for path in lower):
        return "adapter_or_checkpoint"
    if any(path.endswith(".npz") for path in lower):
        return "numpy_artifact"
    return "weighted_artifact"


def evaluate_model(
    info: dict[str, Any],
    readme: str | None,
    *,
    require_structured_eval_for_weights: bool,
) -> dict[str, Any]:
    repo_id = _repo_id(info)
    revision = str(info.get("sha") or "")
    paths = _paths(info)
    readme_text = readme or ""
    weights = weight_files(paths)
    unsafe = unsafe_executable_files(paths)
    evaluation = structured_evaluation(info, paths, readme_text)
    claims = unqualified_claims(readme_text)
    violations: list[dict[str, str]] = []
    warnings: list[dict[str, str]] = []

    if unsafe:
        violations.append(
            {
                "code": "UNSAFE_EXECUTABLE_ARTIFACT",
                "detail": ", ".join(unsafe),
            }
        )
    if claims and not evaluation["present"]:
        violations.append(
            {
                "code": "UNBOUND_FRONTIER_CLAIM",
                "detail": ", ".join(claims),
            }
        )
    if weights and not evaluation["present"]:
        finding = {
            "code": "WEIGHTS_WITHOUT_STRUCTURED_EVALUATION",
            "detail": "No model-index/eval_results or conventional structured results file.",
        }
        if require_structured_eval_for_weights:
            violations.append(finding)
        else:
            warnings.append(finding)
    if not SHA40.fullmatch(revision):
        violations.append({"code": "MISSING_IMMUTABLE_REVISION", "detail": revision or "absent"})
    if "README.md" not in paths:
        warnings.append({"code": "MISSING_ROOT_CARD", "detail": "README.md absent"})
    if not _card_value(info, "license"):
        warnings.append({"code": "MISSING_LICENSE_METADATA", "detail": "license absent"})
    if weights and not (info.get("pipeline_tag") or _card_value(info, "pipeline_tag")):
        warnings.append({"code": "MISSING_PIPELINE_TAG", "detail": "weighted artifact has no pipeline tag"})

    release_static = bool(
        weights
        and evaluation["present"]
        and not unsafe
        and SHA40.fullmatch(revision)
        and "README.md" in paths
        and _card_value(info, "license")
    )
    return {
        "id": repo_id,
        "sha": revision,
        "private": bool(info.get("private")),
        "library_name": info.get("library_name"),
        "pipeline_tag": info.get("pipeline_tag"),
        "artifact_kind": artifact_kind(info, weights),
        "weight_files": weights,
        "unsafe_executable_files": unsafe,
        "structured_evaluation": evaluation,
        "unqualified_frontier_claims": claims,
        "release_static_evidence": "PRESENT" if release_static else "INCOMPLETE",
        "violations": violations,
        "warnings": warnings,
    }


def collect_models(
    org: str,
    token: str | None,
    *,
    require_structured_eval_for_weights: bool,
) -> list[dict[str, Any]]:
    page_limit = 1000
    query = urllib.parse.urlencode({"author": org, "limit": page_limit, "full": "true"})
    listing = _get_json(f"{HF_API}/models?{query}", token)
    if not isinstance(listing, list):
        raise AuditIncomplete("model listing did not return a JSON array")
    if len(listing) >= page_limit:
        raise AuditIncomplete(
            f"model listing reached the {page_limit}-item safety ceiling; pagination is required"
        )
    results = []
    seen: set[str] = set()
    for listed in sorted(listing, key=_repo_id):
        if not isinstance(listed, dict):
            raise AuditIncomplete("model listing contained a non-object entry")
        repo_id = _repo_id(listed)
        if not repo_id.upper().startswith(org.upper() + "/"):
            continue
        if listed.get("private") is True:
            continue
        if repo_id in seen:
            raise AuditIncomplete(f"model listing contained a duplicate ID: {repo_id}")
        seen.add(repo_id)
        encoded = urllib.parse.quote(repo_id, safe="/")
        info = _get_json(f"{HF_API}/models/{encoded}?blobs=true", token)
        if not isinstance(info, dict):
            raise AuditIncomplete(f"model detail was not an object: {repo_id}")
        if info.get("private") is True:
            continue
        revision = str(info.get("sha") or "")
        raw_url = f"{HF_HOST}/{encoded}/resolve/{urllib.parse.quote(revision, safe='')}/README.md"
        readme = _get_text(raw_url, token)
        results.append(
            evaluate_model(
                info,
                readme,
                require_structured_eval_for_weights=require_structured_eval_for_weights,
            )
        )
    return results


def build_report(
    org: str,
    models: list[dict[str, Any]],
    *,
    require_structured_eval_for_weights: bool,
    minimum_models: int,
) -> dict[str, Any]:
    if len(models) < minimum_models:
        raise AuditIncomplete(
            f"coverage collapse: observed {len(models)} models, required at least {minimum_models}"
        )
    kinds = Counter(model["artifact_kind"] for model in models)
    violations = [
        {"model": model["id"], **finding}
        for model in models
        for finding in model["violations"]
    ]
    warnings = [
        {"model": model["id"], **finding}
        for model in models
        for finding in model["warnings"]
    ]
    return {
        "schema": SCHEMA,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "organization": org,
        "status": "VIOLATIONS" if violations else "COMPLETE",
        "policy": {
            "minimum_models": minimum_models,
            "require_structured_eval_for_weights": require_structured_eval_for_weights,
            "static_evidence_is_not": [
                "independent quality certification",
                "state-of-the-art proof",
                "deployment evidence",
                "runtime evidence",
            ],
        },
        "counts": {
            "repositories": len(models),
            "weighted_repositories": sum(bool(model["weight_files"]) for model in models),
            "structured_evaluation": sum(
                bool(model["structured_evaluation"]["present"]) for model in models
            ),
            "static_evidence_present": sum(
                model["release_static_evidence"] == "PRESENT" for model in models
            ),
            "violations": len(violations),
            "warnings": len(warnings),
            "artifact_kinds": dict(sorted(kinds.items())),
        },
        "violations": violations,
        "warnings": warnings,
        "models": models,
    }


def incomplete_report(org: str, error: Exception) -> dict[str, Any]:
    return {
        "schema": SCHEMA,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "organization": org,
        "status": "INCOMPLETE",
        "error": f"{type(error).__name__}: {error}",
        "counts": {},
        "violations": [],
        "warnings": [],
        "models": [],
    }


def render_markdown(report: dict[str, Any]) -> str:
    counts = report.get("counts") or {}
    lines = [
        "# Hugging Face model evidence audit",
        "",
        f"- Organization: `{report.get('organization', 'UNKNOWN')}`",
        f"- Generated: `{report.get('generated_at', 'UNKNOWN')}`",
        f"- Status: **{report.get('status', 'INCOMPLETE')}**",
    ]
    if report.get("status") == "INCOMPLETE":
        lines.extend(["", f"Collection error: `{report.get('error', 'unknown')}`"])
        return "\n".join(lines) + "\n"
    lines.extend(
        [
            f"- Model-type repositories: **{counts.get('repositories', 0)}**",
            f"- Repositories with weights: **{counts.get('weighted_repositories', 0)}**",
            f"- Repositories with structured evaluation: **{counts.get('structured_evaluation', 0)}**",
            f"- Enforced violations: **{counts.get('violations', 0)}**",
            "",
            "Static metadata is not SOTA, independent quality, deployment, or runtime proof.",
        ]
    )
    violations = report.get("violations") or []
    if violations:
        lines.extend(["", "## Enforced findings", "", "| Model | Code | Detail |", "|---|---|---|"])
        for finding in violations[:60]:
            detail = str(finding.get("detail") or "").replace("|", "\\|").replace("\n", " ")
            lines.append(
                f"| `{finding.get('model', 'UNKNOWN')}` | `{finding.get('code', 'UNKNOWN')}` | {detail[:240]} |"
            )
        if len(violations) > 60:
            lines.append(f"\nOnly the first 60 of {len(violations)} findings are shown; use the JSON artifact.")
    return "\n".join(lines) + "\n"


def _write(path: str, text: str) -> None:
    destination = Path(path)
    destination.parent.mkdir(parents=True, exist_ok=True)
    destination.write_text(text, encoding="utf-8", newline="\n")


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--org", default=DEFAULT_ORG)
    parser.add_argument("--report", default="reports/hf-model-evidence-latest.json")
    parser.add_argument("--markdown", default="reports/hf-model-evidence-latest.md")
    parser.add_argument("--min-models", type=int, default=1)
    parser.add_argument("--require-structured-eval-for-weights", action="store_true")
    parser.add_argument("--enforce", action="store_true")
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    try:
        models = collect_models(
            args.org,
            _token(),
            require_structured_eval_for_weights=args.require_structured_eval_for_weights,
        )
        report = build_report(
            args.org,
            models,
            require_structured_eval_for_weights=args.require_structured_eval_for_weights,
            minimum_models=args.min_models,
        )
        code = 1 if args.enforce and report["violations"] else 0
    except Exception as error:  # noqa: BLE001 - any collection gap must fail closed
        report = incomplete_report(args.org, error)
        code = 2
    _write(args.report, json.dumps(report, indent=2, sort_keys=True) + "\n")
    _write(args.markdown, render_markdown(report))
    print(json.dumps(report.get("counts", {}), sort_keys=True))
    if report.get("status") == "INCOMPLETE":
        print(report.get("error", "collection incomplete"), file=sys.stderr)
    return code


if __name__ == "__main__":
    raise SystemExit(main())
