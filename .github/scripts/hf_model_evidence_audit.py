#!/usr/bin/env python3
"""Read-only public Hub artifact/evaluation census. Exit 1 findings, 2 incomplete.

This checks structured evidence shape, never model quality, training completion,
deployment, or inference. Numeric archives and kernel software need their own
qualification contracts and are not treated as transformer checkpoints.
"""
from __future__ import annotations

import argparse
from collections import Counter
from datetime import datetime, timezone
import json
import math
from pathlib import Path, PurePosixPath
import re
import sys
from typing import Any, Iterable
import urllib.error
import urllib.parse
import urllib.request

import yaml

HF_API = "https://huggingface.co/api"
HF_HOST = "https://huggingface.co"
SCHEMA = "szl.hf-model-evidence-audit/v2"
SHA40 = re.compile(r"^[0-9a-f]{40}$")
WEIGHT_SUFFIXES = (".safetensors", ".gguf", ".onnx")
WEIGHT_NAMES = {"adapter_model.bin", "pytorch_model.bin", "tf_model.h5", "flax_model.msgpack"}
SHARDED_WEIGHT = re.compile(r"^(?:pytorch_model|adapter_model)-\d{1,6}-of-\d{1,6}\.bin$", re.I)
UNSAFE_SUFFIXES = (".pkl", ".pickle", ".joblib")
RESULT_NAMES = {"eval_results.json", "results.json", "model-index.yaml", "model-index.yml"}
OVERCLAIM = re.compile(r"\bSOTA\b|state[- ]of[- ]the[- ]art|fully[- ]trained|frontier[- ]class|best[- ]in[- ]class", re.I)
NEGATION_BEFORE = re.compile(
    r"(?:\b(?:no|not|never)\s+(?:yet\s+)?(?:an?\s+)?|"
    r"\b(?:do|does|did|can|could|would)\s+not\s+claim\s+(?:(?:that\s+)?(?:this|it)\s+is\s+|to\s+be\s+)?(?:an?\s+)?|"
    r"\b(?:cannot|can't)\s+(?:claim|establish|prove|be)\s+(?:an?\s+)?|"
    r"\b(?:roadmap|training)\s+target\s*:\s*)$", re.I
)
NEGATION_AFTER = re.compile(
    r"^\s*(?:claim\s+)?(?:(?:is|are|was|were|remains?)\s+)?(?:"
    r"not\s+(?:claimed|established|proven|supported|certified|achieved)|"
    r"unproven|unsupported|uncertified|(?:a\s+)?roadmap(?:\s+target)?|target\s+only)\b", re.I
)


class AuditIncomplete(RuntimeError):
    """The inventory could not be observed within its declared bounds."""


def _read_url(url: str, maximum: int) -> bytes:
    # Deliberately unauthenticated: this is the public projection and emits no
    # private IDs even when the runner has credentials for a different workflow.
    request = urllib.request.Request(url, headers={"User-Agent": "szl-hf-evidence-audit/2"})
    with urllib.request.urlopen(request, timeout=45) as response:
        content = response.read(maximum + 1)
    if len(content) > maximum:
        raise AuditIncomplete("response exceeds bounded metadata read")
    return content


def _get_json(url: str) -> Any:
    return json.loads(_read_url(url, 16 * 1024 * 1024))


def _get_text(url: str) -> str | None:
    try:
        return _read_url(url, 2 * 1024 * 1024).decode("utf-8")
    except urllib.error.HTTPError as error:
        if error.code == 404:
            return None
        raise


def _repo_id(item: dict[str, Any]) -> str:
    return str(item.get("id") or item.get("modelId") or "")


def _paths(info: dict[str, Any]) -> list[str]:
    paths = []
    for sibling in info.get("siblings") or []:
        if isinstance(sibling, dict) and sibling.get("rfilename"):
            path = str(sibling["rfilename"])
            if "\\" in path or path.startswith("/") or ".." in PurePosixPath(path).parts:
                raise AuditIncomplete("unsafe Hub metadata path")
            paths.append(path)
    return sorted(set(paths))


def weight_files(paths: Iterable[str]) -> list[str]:
    return sorted({path for path in paths if (
        PurePosixPath(path).name.lower() in WEIGHT_NAMES
        or SHARDED_WEIGHT.fullmatch(PurePosixPath(path).name)
        or path.lower().endswith(WEIGHT_SUFFIXES)
    )})


def unsafe_executable_files(paths: Iterable[str]) -> list[str]:
    return sorted({path for path in paths if (
        PurePosixPath(path).name.lower() == "training_args.bin"
        or path.lower().endswith(UNSAFE_SUFFIXES)
    )})


def _nonempty(value: Any) -> bool:
    return isinstance(value, str) and bool(value.strip())


def _finite_score(value: Any) -> bool:
    return isinstance(value, (float, int)) and not isinstance(value, bool) and math.isfinite(value)


def _hub_results(value: Any) -> list[dict[str, Any]]:
    """Accept complete Hub model-index records; a name/marker alone is no result."""
    valid = []
    if not isinstance(value, list):
        return valid
    for model in value:
        if not isinstance(model, dict) or not _nonempty(model.get("name")):
            continue
        results = model.get("results")
        if not isinstance(results, list):
            continue
        for result in results:
            if not isinstance(result, dict):
                continue
            task, dataset, metrics = result.get("task"), result.get("dataset"), result.get("metrics")
            if not (isinstance(task, dict) and _nonempty(task.get("type"))
                    and isinstance(dataset, dict) and _nonempty(dataset.get("type"))
                    and isinstance(metrics, list)):
                continue
            for metric in metrics:
                if isinstance(metric, dict) and _nonempty(metric.get("type")) and _finite_score(metric.get("value")):
                    valid.append({"task": task["type"], "dataset": dataset["type"],
                                  "metric": metric["type"], "value": metric["value"]})
    return valid


def _flat_results(value: Any) -> list[dict[str, Any]]:
    """Validate Hugging Face EvalResult field names, not arbitrary score blobs."""
    if not isinstance(value, list):
        return []
    return [{"task": item["task_type"], "dataset": item["dataset_type"],
             "metric": item["metric_type"], "value": item["metric_value"]}
            for item in value if isinstance(item, dict)
            and all(_nonempty(item.get(key)) for key in ("task_type", "dataset_type", "metric_type"))
            and _finite_score(item.get("metric_value"))]


def _current_hub_results(value: Any) -> list[dict[str, Any]]:
    """Current .eval_results/*.yaml shape, without asserting token verification."""
    valid = []
    if not isinstance(value, list):
        return valid
    for item in value:
        if not isinstance(item, dict) or not isinstance(item.get("dataset"), dict):
            continue
        dataset = item["dataset"]
        if not (_nonempty(dataset.get("id")) and _nonempty(dataset.get("task_id"))
                and _finite_score(item.get("value"))):
            continue
        if "revision" in dataset and not _nonempty(dataset["revision"]):
            continue
        if any(key in item and not _nonempty(item[key]) for key in ("verifyToken", "date")):
            continue
        if "notes" in item and not isinstance(item["notes"], str):
            continue
        source = item.get("source")
        if "source" in item and not (isinstance(source, dict) and _nonempty(source.get("url"))):
            continue
        valid.append({"task": dataset["task_id"], "dataset": dataset["id"], "metric": "benchmark-task-value",
                      "value": item["value"], "verification": "NOT_VERIFIED_BY_THIS_AUDIT"})
    return valid


def _records(value: Any) -> list[dict[str, Any]]:
    if isinstance(value, dict):
        return (_hub_results(value.get("model-index")) + _hub_results(value.get("model_index"))
                + _flat_results(value.get("eval_results")))
    return _hub_results(value) + _flat_results(value)


def _result_path(path: str) -> bool:
    return (PurePosixPath(path).name.lower() in RESULT_NAMES
            or (PurePosixPath(path).parent.as_posix() == ".eval_results"
                and path.lower().endswith((".yaml", ".yml"))))


def structured_evaluation(info: dict[str, Any], documents: dict[str, str | None]) -> dict[str, Any]:
    card = info.get("cardData") or info.get("card_data") or {}
    records = _records(card)
    sources = ["Hub cardData"] if records else []
    invalid = []
    for path, text in documents.items():
        if text is None:
            invalid.append({"path": path, "reason": "missing at immutable revision"})
            continue
        try:
            parsed = json.loads(text) if path.lower().endswith(".json") else yaml.safe_load(text)
            found = _current_hub_results(parsed) if PurePosixPath(path).parent.as_posix() == ".eval_results" else _records(parsed)
        except (ValueError, TypeError, yaml.YAMLError, RecursionError):
            invalid.append({"path": path, "reason": "malformed structured data"})
            continue
        if found:
            records.extend(found)
            sources.append(path)
        else:
            invalid.append({"path": path, "reason": "no valid task/dataset/metric/finite-score record"})
    return {"present": bool(records), "record_count": len(records), "sources": sources,
            "records": records, "invalid_documents": invalid}


def unqualified_claims(readme: str) -> list[str]:
    # Each claim gets only its own sentence and an immediate grammatical
    # qualification. A nearby negation about a baseline cannot excuse a release.
    claims = []
    for normalized in re.split(r"[.!?]+", re.sub(r"\s+", " ", readme)):
        for match in OVERCLAIM.finditer(normalized):
            before, after = normalized[:match.start()], normalized[match.end():]
            if not NEGATION_BEFORE.search(before) and not NEGATION_AFTER.search(after):
                claims.append(match.group(0))
    return sorted(set(claims), key=str.lower)


def artifact_kind(info: dict[str, Any], paths: list[str], weights: list[str]) -> str:
    lower = [path.lower() for path in weights]
    if any(path.endswith(".gguf") for path in lower):
        return "gguf_derivative"
    if any(PurePosixPath(path).name.lower().startswith("adapter_model") for path in weights):
        return "adapter"
    if weights:
        return "checkpoint_or_export"
    if any(path.lower().endswith(".npz") for path in paths):
        return "numeric_fixture_or_embedding_table"
    card = info.get("cardData") or {}
    library = info.get("library_name") or (card.get("library_name") if isinstance(card, dict) else None)
    return "kernel_software" if library == "kernels" else "recipe_or_documentation"


def evaluate_model(info: dict[str, Any], readme: str | None, *,
                   require_structured_eval_for_weights: bool,
                   result_documents: dict[str, str | None] | None = None) -> dict[str, Any]:
    paths = _paths(info)
    weights, unsafe = weight_files(paths), unsafe_executable_files(paths)
    evaluation = structured_evaluation(info, result_documents or {})
    claims = unqualified_claims(readme or "")
    revision = str(info.get("sha") or "")
    kind = artifact_kind(info, paths, weights)
    violations, warnings = [], []
    if unsafe:
        violations.append({"code": "UNSAFE_EXECUTABLE_ARTIFACT", "detail": ", ".join(unsafe)})
    if claims:
        violations.append({"code": "UNQUALIFIED_FRONTIER_CLAIM", "detail": ", ".join(claims)})
    if weights and not evaluation["present"]:
        target = violations if require_structured_eval_for_weights else warnings
        target.append({"code": "WEIGHTS_WITHOUT_STRUCTURED_EVALUATION",
                       "detail": "No validated task/dataset/metric/finite-score record."})
    if not SHA40.fullmatch(revision):
        violations.append({"code": "MISSING_IMMUTABLE_REVISION", "detail": revision or "absent"})
    for invalid in evaluation["invalid_documents"]:
        warnings.append({"code": "INVALID_EVALUATION_DOCUMENT", "detail": invalid["path"] + ": " + invalid["reason"]})
    if kind in {"numeric_fixture_or_embedding_table", "kernel_software"}:
        warnings.append({"code": "OWN_CONTRACT_REVIEW_REQUIRED",
                         "detail": "Needs numeric/kernel loader, correctness and benchmark contract review."})
    card = info.get("cardData") or {}
    license_present = isinstance(card, dict) and bool(card.get("license"))
    if not license_present:
        warnings.append({"code": "MISSING_LICENSE_METADATA", "detail": "license absent"})
    if readme is None:
        warnings.append({"code": "MISSING_ROOT_CARD", "detail": "README.md absent at immutable revision"})
    static = bool(weights and evaluation["present"] and not violations and readme is not None and license_present)
    return {"id": _repo_id(info), "sha": revision, "private": bool(info.get("private")),
            "artifact_kind": kind, "weight_files": weights,
            "numeric_archive_files": [path for path in paths if path.lower().endswith(".npz")],
            "unsafe_executable_files": unsafe, "structured_evaluation": evaluation,
            "unqualified_frontier_claims": claims,
            "release_static_evidence": "PRESENT" if static else "INCOMPLETE",
            "violations": violations, "warnings": warnings}


def collect_models(org: str, *, require_structured_eval_for_weights: bool) -> list[dict[str, Any]]:
    query = urllib.parse.urlencode({"author": org, "limit": 1000, "full": "true"})
    listing = _get_json(f"{HF_API}/models?{query}")
    if not isinstance(listing, list) or len(listing) >= 1000:
        raise AuditIncomplete("model listing invalid or at 1000-item ceiling; pagination required")
    models, seen = [], set()
    for listed in listing:
        if not isinstance(listed, dict):
            raise AuditIncomplete("model listing contained a non-object")
        repo_id = _repo_id(listed)
        if not repo_id.upper().startswith(org.upper() + "/") or listed.get("private") is True:
            continue
        if repo_id in seen:
            raise AuditIncomplete("duplicate model ID: " + repo_id)
        seen.add(repo_id)
        encoded = urllib.parse.quote(repo_id, safe="/")
        info = _get_json(f"{HF_API}/models/{encoded}?blobs=true")
        if not isinstance(info, dict) or _repo_id(info) != repo_id or not SHA40.fullmatch(str(info.get("sha") or "")):
            raise AuditIncomplete("invalid immutable model identity: " + repo_id)
        revision = info["sha"]
        info = _get_json(f"{HF_API}/models/{encoded}/revision/{revision}?blobs=true")
        if not isinstance(info, dict) or _repo_id(info) != repo_id or info.get("sha") != revision:
            raise AuditIncomplete("pinned model identity changed: " + repo_id)
        if info.get("private") is True:
            continue
        base = f"{HF_HOST}/{encoded}/resolve/{revision}/"
        paths = _paths(info)
        readme = _get_text(base + "README.md") if "README.md" in paths else None
        documents = {path: _get_text(base + urllib.parse.quote(path, safe="/")) for path in paths
                     if _result_path(path)}
        models.append(evaluate_model(info, readme, require_structured_eval_for_weights=require_structured_eval_for_weights,
                                     result_documents=documents))
    return sorted(models, key=lambda item: item["id"])


def build_report(org: str, models: list[dict[str, Any]], *,
                 require_structured_eval_for_weights: bool, minimum_models: int) -> dict[str, Any]:
    if len(models) < minimum_models:
        raise AuditIncomplete(f"coverage collapse: {len(models)} observed, at least {minimum_models} required")
    violations = [{"model": model["id"], **item} for model in models for item in model["violations"]]
    warnings = [{"model": model["id"], **item} for model in models for item in model["warnings"]]
    return {"schema": SCHEMA, "generated_at": datetime.now(timezone.utc).isoformat(), "organization": org,
            "status": "VIOLATIONS" if violations else "COMPLETE",
            "policy": {"scope": "public model-type repositories", "minimum_models": minimum_models,
                       "require_structured_eval_for_weights": require_structured_eval_for_weights,
                       "static_evidence_is_not": ["quality certification", "SOTA proof", "training completion",
                                                  "deployment evidence", "runtime evidence"]},
            "counts": {"repositories": len(models), "weighted_repositories": sum(bool(m["weight_files"]) for m in models),
                       "structured_evaluation": sum(m["structured_evaluation"]["present"] for m in models),
                       "static_evidence_present": sum(m["release_static_evidence"] == "PRESENT" for m in models),
                       "violations": len(violations), "warnings": len(warnings),
                       "artifact_kinds": dict(sorted(Counter(m["artifact_kind"] for m in models).items()))},
            "violations": violations, "warnings": warnings, "models": models}


def render_markdown(report: dict[str, Any]) -> str:
    lines = ["# Public Hub model evidence census", "", f"Status: {report['status']}",
             f"Collected: {report['generated_at']}", "",
             "This is evidence-shape review, not quality, training, deployment or runtime proof.", ""]
    if report["status"] == "INCOMPLETE":
        lines.append("Collection error: " + report["error"])
    else:
        lines.append("Counts: " + json.dumps(report["counts"], sort_keys=True))
        lines.extend(["", "| Repository | Finding | Detail |", "| --- | --- | --- |"])
        for item in report["violations"][:60]:
            detail = item["detail"].replace("|", "\\|").replace("\n", " ")[:240]
            lines.append(f"| `{item['model']}` | `{item['code']}` | {detail} |")
        lines.append("\nThe JSON artifact includes every finding, warning and immutable Hub revision.")
    return "\n".join(lines) + "\n"


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--org", default="SZLHOLDINGS")
    parser.add_argument("--report", default="reports/hf-model-evidence-latest.json")
    parser.add_argument("--markdown", default="reports/hf-model-evidence-latest.md")
    parser.add_argument("--min-models", type=int, default=1)
    parser.add_argument("--require-structured-eval-for-weights", action="store_true")
    parser.add_argument("--enforce", action="store_true")
    args = parser.parse_args(argv)
    try:
        models = collect_models(args.org, require_structured_eval_for_weights=args.require_structured_eval_for_weights)
        report = build_report(args.org, models, require_structured_eval_for_weights=args.require_structured_eval_for_weights,
                              minimum_models=args.min_models)
        code = 1 if args.enforce and report["violations"] else 0
    except Exception as error:  # Any collection gap has a distinct unavailable outcome.
        report = {"schema": SCHEMA, "generated_at": datetime.now(timezone.utc).isoformat(), "organization": args.org,
                  "status": "INCOMPLETE", "error": f"{type(error).__name__}: {error}", "counts": {},
                  "models": [], "violations": [], "warnings": []}
        code = 2
    for path, text in ((args.report, json.dumps(report, indent=2, sort_keys=True) + "\n"),
                       (args.markdown, render_markdown(report))):
        destination = Path(path)
        destination.parent.mkdir(parents=True, exist_ok=True)
        destination.write_text(text, encoding="utf-8", newline="\n")
    print(json.dumps(report["counts"], sort_keys=True))
    if report["status"] == "INCOMPLETE":
        print(report["error"], file=sys.stderr)
    return code


if __name__ == "__main__":
    raise SystemExit(main())
