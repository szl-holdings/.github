#!/usr/bin/env python3
"""Render a Hugging Face card from a vars file with the shared SZL template.

    python hf-card/render.py hf/card.yaml --out README.md
    python hf-card/render.py hf/card.yaml --out README.md --check
    python hf-card/render.py hf/card.yaml --out README.md --source-sha "$GITHUB_SHA"

The vars file is committed in the asset's source repository. render.py
validates it, renders hf-card/template.md.j2, then lints the result with
hf-card/lint.py. It refuses to write a card that fails the lint, so a card it
writes never carries a MEASURED label without a receipt link.

--check renders in memory and exits 1 when the file at --out differs, so a
source repository can keep its committed card equal to its vars file.
--source-sha stamps the commit the card was rendered from; the mirror workflow
passes it at publish time (decision D4). Leave it out for the committed copy.

Exit codes: 0 written or up to date, 1 validation, lint or drift failure,
2 usage error.
"""

from __future__ import annotations

import argparse
import datetime as dt
import re
import sys
from urllib.parse import urlsplit
from pathlib import Path
from typing import Any

import jinja2
import yaml

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))

import lint  # noqa: E402  (sibling module, resolved from this file's directory)

TEMPLATE = HERE / "template.md.j2"
CLAIM_LABELS = (
    "MEASURED",
    "REPORTED",
    "UNVERIFIED",
    "UNRATIFIED",
    "DEGRADED",
    "BLOCKED",
    "UNAVAILABLE",
    "NOT_CLAIMED",
)
VARS_KEYS = {
    "type", "repo_id", "title", "summary", "front_matter", "sections", "claims", "limits",
    "release", "dataset", "space", "kernel", "overview", "links", "inference", "support_request",
}
SHA = re.compile(r"^[0-9a-f]{40}$")


class VarsError(Exception):
    pass


def _require(condition: bool, message: str) -> None:
    if not condition:
        raise VarsError(message)


def load_vars(path: Path) -> dict[str, Any]:
    try:
        data = yaml.safe_load(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, yaml.YAMLError) as exc:
        raise VarsError(f"cannot read vars file {path}: {exc}") from None
    _require(isinstance(data, dict), "vars file must be a YAML mapping")
    unknown = sorted(set(data) - VARS_KEYS)
    _require(not unknown, f"unknown vars key(s): {unknown}")
    for key in ("type", "repo_id", "title", "summary", "front_matter"):
        _require(key in data, f"vars file is missing {key!r}")
    _require(data["type"] in lint.CARD_TYPES, f"type must be one of {lint.CARD_TYPES}")
    _require(isinstance(data["repo_id"], str) and data["repo_id"].startswith("SZLHOLDINGS/"),
             "repo_id must be SZLHOLDINGS/<name> (org casing is literal)")
    _require(isinstance(data["front_matter"], dict), "front_matter must be a mapping")
    for key in ("title", "summary"):
        _require(isinstance(data[key], str) and data[key].strip(), f"{key} must be a non-empty string")
    for section in data.get("sections") or []:
        _require(isinstance(section, dict) and set(section) == {"heading", "body"},
                 "each section needs exactly heading and body")
        _require(all(isinstance(section[k], str) and section[k].strip() for k in section),
                 "section heading and body must be non-empty strings")
    for item in data.get("limits") or []:
        _require(isinstance(item, str) and item.strip(), "each limit must be a non-empty string")
    for block in ("dataset", "space", "kernel"):
        _require(isinstance(data.get(block, {}), dict), f"{block} must be a mapping")
    check_presentation(data)
    return data


def check_presentation(data: dict[str, Any]) -> None:
    overview = data.get("overview", {})
    _require(isinstance(overview, dict) and set(overview) <= {"artifact_type", "stage"},
             "overview supports only artifact_type and stage")
    for key, value in overview.items():
        _require(isinstance(value, str) and value.strip() and len(value) <= 100
                 and not any(c in value for c in "\n\r<>|"),
                 f"overview.{key} must be a short plain-text label")
    links = data.get("links", {})
    _require(isinstance(links, dict) and set(links) <= {"try", "build", "evidence"},
             "links supports only try, build and evidence")
    for key, value in links.items():
        _require(isinstance(value, str), f"links.{key} must be an HTTPS URL")
        parsed = urlsplit(value)
        _require(parsed.scheme == "https" and bool(parsed.hostname)
                 and not parsed.username and not parsed.password
                 and not any(c.isspace() or c in "<>()\\" for c in value),
                 f"links.{key} must be an unambiguous HTTPS URL")
    inference = data.get("inference")
    if inference is not None:
        _require(data.get("type") == "model", "inference observations belong to model cards")
        _require(isinstance(inference, dict) and set(inference) == {
            "state", "providers", "observed_at", "hub_revision", "source_url"},
            "inference needs exact state, providers, observed_at, hub_revision and source_url")
        _require(inference["state"] in {
            "NO_PROVIDER_MAPPING", "PROVIDER_MAPPING_REPORTED", "UNAVAILABLE"},
            "inference.state is not a supported provider observation")
        providers = inference["providers"]
        _require(isinstance(providers, list) and all(isinstance(provider, str)
                         and re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_-]{0,79}", provider)
                         for provider in providers)
                 and len(providers) == len(set(providers)), "inference.providers must be unique provider IDs")
        _require(bool(providers) == (inference["state"] == "PROVIDER_MAPPING_REPORTED"),
                 "provider state and provider names disagree")
        _require(isinstance(inference["hub_revision"], str)
                 and SHA.fullmatch(inference["hub_revision"]) is not None,
                 "inference.hub_revision must be an immutable Hub revision")
        _require(isinstance(inference["observed_at"], str)
                 and re.fullmatch(r"\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(?:\.\d+)?(?:Z|\+00:00)",
                                  inference["observed_at"]) is not None,
                 "inference.observed_at must be a UTC observation timestamp")
        try:
            dt.datetime.fromisoformat(inference["observed_at"].replace("Z", "+00:00"))
        except ValueError:
            raise VarsError("inference.observed_at is not a valid calendar date") from None
        prefix = "https://huggingface.co/api/models/" + str(data["repo_id"])
        _require(isinstance(inference["source_url"], str)
                 and inference["source_url"] in {
                     prefix + "?expand=inferenceProviderMapping",
                     prefix + "?expand[]=inferenceProviderMapping",
                     prefix + "?expand%5B%5D=inferenceProviderMapping",
                     prefix + "?expand[]=inferenceProviderMapping&expand[]=sha",
                     prefix + "?expand%5B%5D=inferenceProviderMapping&expand%5B%5D=sha"},
                 "inference.source_url must observe this exact model's provider mapping")
    request = data.get("support_request")
    if request is not None:
        _require(data.get("type") == "model", "provider support requests belong to model cards")
        _require(isinstance(request, dict) and set(request) == {
            "model_id", "model_revision", "url", "requested_at", "verified_readback", "request_state"},
            "support_request needs exact model identity, URL, date, readback and request state")
        _require(request["model_id"] == data["repo_id"], "support request belongs to another model")
        _require(isinstance(request["model_revision"], str)
                 and SHA.fullmatch(request["model_revision"]) is not None,
                 "support request must bind the submitted model revision")
        _require(request["verified_readback"] is True and
                 request["request_state"] == "SUBMITTED_RESEARCH_COMPATIBILITY_REVIEW",
                 "support requested requires verified submission evidence")
        _require(isinstance(request["url"], str) and re.fullmatch(
            r"https://huggingface\.co/spaces/huggingface/InferenceSupport/discussions/[1-9][0-9]*",
            request["url"]) is not None, "support request must link the official submitted discussion")
        _require(isinstance(request["requested_at"], str) and re.fullmatch(
            r"\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(?:\.\d+)?(?:Z|\+00:00)",
            request["requested_at"]) is not None, "support request needs a UTC submission date")
        try:
            dt.datetime.fromisoformat(request["requested_at"].replace("Z", "+00:00"))
        except ValueError:
            raise VarsError("support request has an invalid submission date") from None



def check_claims(claims: list[Any], source_repo: str | None) -> None:
    for i, claim in enumerate(claims):
        where = f"claims[{i}]"
        _require(isinstance(claim, dict), f"{where} must be a mapping")
        unknown = sorted(set(claim) - {"label", "claim", "receipt"})
        _require(not unknown, f"{where} has unknown key(s) {unknown}")
        _require(claim.get("label") in CLAIM_LABELS, f"{where}.label must be one of {CLAIM_LABELS}")
        _require(isinstance(claim.get("claim"), str) and claim["claim"].strip(), f"{where}.claim is empty")
        receipt = claim.get("receipt")
        if claim["label"] == "MEASURED":
            _require(receipt is not None, f"{where} is MEASURED but links no receipt (decision D10)")
        if receipt is not None:
            repo = lint.receipt_repo(receipt) if isinstance(receipt, str) else None
            _require(repo is not None,
                     f"{where}.receipt must be https://github.com/szl-holdings/<repo>/blob/<40-hex sha>/<path>")
            _require(source_repo is None or repo == source_repo,
                     f"{where}.receipt points outside the source repo szl-holdings/{source_repo}")


def front_matter_yaml(front_matter: dict[str, Any]) -> str:
    text = yaml.safe_dump(front_matter, sort_keys=False, allow_unicode=True,
                          default_flow_style=False, width=1000)
    _require(yaml.safe_load(text) == front_matter, "front matter does not round-trip through YAML")
    return text


def _cell(value: Any) -> str:
    return " ".join(str(value).split()).replace("|", "\\|")


def render(data: dict[str, Any], *, source_sha: str | None = None, vars_path: str = "hf/card.yaml") -> str:
    check_presentation(data)
    front_matter = dict(data["front_matter"])
    szl = front_matter.get("szl")
    if source_sha is not None:
        _require(SHA.fullmatch(source_sha) is not None, "--source-sha must be a 40-hex commit sha")
        _require(isinstance(szl, dict), "front_matter.szl must be a mapping")
        front_matter["szl"] = {**szl, "source_sha": source_sha}
    errors = lint.validate_front_matter(front_matter, data["type"])
    _require(not errors, "front matter fails hf-card/schema.json:\n  " + "\n  ".join(errors))
    source_repo = lint.source_repo_name(front_matter)
    claims = data.get("claims") or []
    _require(isinstance(claims, list), "claims must be a list")
    check_claims(claims, source_repo)
    release = data.get("release")
    if release is not None:
        _require(isinstance(release, dict) and set(release) == {"tag", "source_sha"},
                 "release needs exactly tag and source_sha")
        _require(SHA.fullmatch(str(release["source_sha"])) is not None, "release.source_sha must be 40-hex")

    env = jinja2.Environment(
        loader=jinja2.FileSystemLoader(str(HERE)),
        undefined=jinja2.StrictUndefined,
        autoescape=False,
        keep_trailing_newline=True,
        trim_blocks=True,
        lstrip_blocks=True,
    )
    env.filters["cell"] = _cell
    context: dict[str, Any] = {
        "type": data["type"],
        "repo_id": data["repo_id"],
        "title": data["title"].strip(),
        "summary": data["summary"].strip(),
        "fm": front_matter,
        "front_matter_yaml": front_matter_yaml(front_matter),
        "sections": data.get("sections") or [],
        "claims": claims,
        "limits": data.get("limits") or [],
        "dataset": data.get("dataset") or {},
        "space": data.get("space") or {},
        "kernel": data.get("kernel") or {},
        "source_sha": source_sha,
        "vars_path": vars_path,
        "overview": data.get("overview") or {},
        "links": data.get("links") or {},
        "inference": data.get("inference") or {},
        "support_request": data.get("support_request") or {},
    }
    if release is not None:
        context["release"] = release
    try:
        text = env.get_template(TEMPLATE.name).render(**context)
    except jinja2.TemplateError as exc:
        raise VarsError(f"template rendering failed: {exc}") from None
    text = re.sub(r"\n{3,}", "\n\n", text).rstrip("\n") + "\n"
    report = lint.lint_text(text, data["type"], "rendered card")
    _require(report.ok, "rendered card fails hf-card/lint.py:\n  "
             + "\n  ".join(f.render("rendered card") for f in report.findings))
    return text


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("vars", type=Path, help="vars file (YAML) committed in the source repository")
    parser.add_argument("--out", type=Path, required=True, help="card to write or check, usually README.md")
    parser.add_argument("--source-sha", help="40-hex commit the card is rendered from (publish time only)")
    parser.add_argument("--vars-label", help="path to show in the card marker (default: the vars argument)")
    parser.add_argument("--check", action="store_true", help="exit 1 when --out differs from the rendering")
    args = parser.parse_args(argv)
    try:
        data = load_vars(args.vars)
        text = render(data, source_sha=args.source_sha,
                      vars_path=args.vars_label or args.vars.as_posix())
    except VarsError as exc:
        print(f"hf-card render: {exc}", file=sys.stderr)
        return 1
    except (lint.CardError, lint.SchemaError) as exc:
        print(f"hf-card render: {exc}", file=sys.stderr)
        return 2
    if args.check:
        try:
            current = args.out.read_bytes().decode("utf-8")
        except (OSError, UnicodeDecodeError):
            current = None
        if current != text:
            print(f"hf-card render: {args.out} differs from {args.vars}; re-run render.py and commit", file=sys.stderr)
            return 1
        print(f"{args.out}: up to date with {args.vars}")
        return 0
    args.out.write_text(text, encoding="utf-8", newline="\n")
    print(f"{args.out}: rendered from {args.vars} ({data['type']})")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
