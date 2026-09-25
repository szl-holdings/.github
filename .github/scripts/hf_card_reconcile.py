#!/usr/bin/env python3
"""Reconcile declared Hub card fields with exact, unsigned plan/apply receipts.

Default is plan-only. Body replacement requires --allow-body-replace in both
plan and apply. Apply requires --expected-plan to bind reviewed source and Hub bytes.
An existing governance section is completed in place with only its missing marker
lines; a second section is never added, and duplicate sections fail closed.
Apply authenticates with --auth token (the first nonempty TOKEN_KEYS secret, used
for every target) or --auth oidc (one Trusted Publisher token per target, read from
HF_OIDC_TOKEN_<RESOURCE>; a missing target token fails closed before any request).
Only the standard library is used; credentials are never retained in receipts.
"""
from __future__ import annotations

import argparse
import base64
import hashlib
import json
import os
from pathlib import Path
import re
import sys
import time
import urllib.error
import urllib.request
from datetime import datetime, timezone

HUB = "https://huggingface.co"
SCHEMA = "szl.governance.hf_card_reconcile/v1"
ORG = "SZLHOLDINGS"
MEASURED, REPORTED, UNAVAILABLE = "MEASURED", "REPORTED", "UNAVAILABLE"
SHA = re.compile(r"[0-9a-f]{40}")
HUB_TOKEN_SHAPE = re.compile(r"hf_[A-Za-z0-9._-]+")
SCALAR = re.compile(r"^([A-Za-z_][A-Za-z0-9_-]*):[ \t]*(.*)$")
TOKEN_KEYS = ("HF_CARD_WRITE_TOKEN", "HF_ORG_TOKEN", "HF_ORG_TOKEN1", "HF_TOKEN", "HF_WRITE_TOKEN")
OIDC_ENV_PREFIX = "HF_OIDC_TOKEN_"


def digest(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def hub_request(method: str, path: str, token: str | None,
                body: bytes | None = None, content_type: str | None = None):
    headers = {"User-Agent": "szl-hf-card-reconcile/2.0"}
    if token:
        headers["Authorization"] = f"Bearer {token}"
    if content_type:
        headers["Content-Type"] = content_type
    req = urllib.request.Request(HUB + path, data=body, headers=headers, method=method)
    # A timed-out POST may already have committed; never repeat ambiguous writes.
    limit = 3 if method == "GET" else 1
    for attempt in range(limit):
        try:
            with urllib.request.urlopen(req, timeout=45) as resp:
                return resp.read().decode("utf-8"), resp.status
        except urllib.error.HTTPError as exc:
            detail = exc.read().decode("utf-8", "replace")[:400]
            if token:
                detail = detail.replace(token, "[REDACTED]")
            if exc.code in (429, 500, 502, 503) and attempt + 1 < limit:
                time.sleep(4 * (attempt + 1))
                continue
            return detail, exc.code
        except (urllib.error.URLError, TimeoutError, OSError, UnicodeError):
            if attempt + 1 < limit:
                time.sleep(3)
                continue
            return "request failed or response was not UTF-8", 0
    return "request failed", 0


def split_card(text: str) -> tuple[str, str, str, str]:
    opening = re.match(r"\A---(?:\r\n|\n)", text)
    if not opening:
        raise ValueError("no YAML front matter found")
    closing = re.search(r"(?m)^---[ \t]*(?:\r\n|\n|\Z)", text[opening.end():])
    if not closing:
        raise ValueError("unterminated YAML front matter")
    start = opening.end() + closing.start()
    end = opening.end() + closing.end()
    return text[:opening.end()], text[opening.end():start], text[start:end], text[end:]


def split_front_matter(text: str) -> tuple[str, str]:
    _, fm, _, body = split_card(text)
    return fm, body


def scalar_value(raw: str) -> str:
    value = raw.strip()
    if not value or value.startswith(("|", ">", "[", "{", "&", "*", "!")):
        raise ValueError("target field is not a supported single-line scalar")
    if value.startswith('"'):
        try:
            parsed, end = json.JSONDecoder().raw_decode(value)
        except ValueError as exc:
            raise ValueError("unsupported quoted scalar") from exc
        tail = value[end:].strip()
        if not isinstance(parsed, str) or (tail and not tail.startswith("#")):
            raise ValueError("unsupported quoted scalar")
        return parsed
    if value.startswith("'"):
        match = re.fullmatch(r"'((?:[^']|'')*)'[ \t]*(?:#.*)?", value)
        if not match:
            raise ValueError("unsupported quoted scalar")
        return match.group(1).replace("''", "'")
    return re.split(r"[ \t]+#", value, maxsplit=1)[0].rstrip()


def set_scalar(fm: str, key: str, value: str) -> tuple[str, bool]:
    """Change one scalar or append after all existing YAML blocks."""
    lines = fm.splitlines(keepends=True)
    positions = []
    for i, line in enumerate(lines):
        raw = line.rstrip("\r\n")
        if re.match(rf"^[\"']{re.escape(key)}[\"']\s*:", raw):
            raise ValueError(f"quoted target key is unsupported: {key}")
        match = SCALAR.match(raw)
        if match and match.group(1) == key:
            positions.append((i, match.group(2)))
    if len(positions) > 1:
        raise ValueError(f"duplicate target field: {key}")
    encoded = value if re.fullmatch(r"[A-Za-z0-9_.-]+", value) else json.dumps(value, ensure_ascii=False)
    newline = "\r\n" if "\r\n" in fm else "\n"
    if positions:
        i, raw = positions[0]
        current = scalar_value(raw)
        for following in lines[i + 1:]:
            if not following.strip() or following.lstrip().startswith("#"):
                continue
            if following.startswith((" ", "\t", "-")):
                raise ValueError(f"target field has block or continuation content: {key}")
            break
        if current == value:
            return fm, False
        ending = "\r\n" if lines[i].endswith("\r\n") else "\n" if lines[i].endswith("\n") else ""
        lines[i] = f"{key}: {encoded}{ending}"
        return "".join(lines), True
    prefix = fm if not fm or fm.endswith("\n") else fm + newline
    return prefix + f"{key}: {encoded}{newline}", True


def stamp_lines(asset: dict) -> list[tuple[tuple[str, ...], str]]:
    """Governance marker lines, each with the markers it carries."""
    source = asset["source_repo"]
    return [
        ((asset["repo_id"],), f"- Hub repository: `{asset['repo_id']}`"),
        (("https://github.com/" + source,), f"- Source of truth: [github.com/{source}](https://github.com/{source})"),
        (("MEASURED / REPORTED / UNKNOWN / UNAVAILABLE",),
         "- Doctrine labels in force: MEASURED / REPORTED / UNKNOWN / UNAVAILABLE"),
        (("UNSIGNED_HONEST", "DSSE"), "- Receipts remain UNSIGNED_HONEST until the DSSE lane signs"),
    ]


def stamp_block(asset: dict, defaults: dict, newline: str = "\n") -> str:
    return newline.join([defaults.get("stamp_heading", "## Governance"), "",
                         *(line for _, line in stamp_lines(asset)), ""])


def has_stamp(body: str, asset: dict, defaults: dict | None = None) -> bool:
    heading = (defaults or {}).get("stamp_heading", "## Governance")
    return heading in body and all(marker in body for markers, _ in stamp_lines(asset) for marker in markers)


ATX = re.compile(r"^ {0,3}(#{1,6})(?:[ \t]+(.*?))?[ \t]*$")
FENCE_OPEN = re.compile(r"^ {0,3}(`{3,}|~{3,})(.*)$")
FENCE_CLOSE = re.compile(r"^ {0,3}(`{3,}|~{3,})[ \t]*$")
SETEXT_UNDERLINE = re.compile(r"^ {0,3}(?:=+|-+)[ \t]*$")
LIST_ITEM = re.compile(r"^ {0,3}[-*+][ \t]")


def atx_heading(line: str) -> tuple[int, str] | None:
    match = ATX.match(line.rstrip("\r\n"))
    if not match:
        return None
    return len(match.group(1)), re.sub(r"(?:^|[ \t]+)#+$", "", match.group(2) or "").strip()


def markdown_lines(body: str) -> tuple[list[str], list[str]]:
    """Split on LF only (so lines rejoin to the exact bytes) and classify each line.

    Kinds: "text", "code" (fence opener or fenced content), "close" (fence closer).
    """
    lines = [m.group(0) for m in re.finditer(r"[^\n]*\n|[^\n]+\Z", body)]
    kinds, fence = [], None
    for line in lines:
        raw = line.rstrip("\r\n")
        if fence:
            closing = FENCE_CLOSE.match(raw)
            if closing and closing.group(1)[0] == fence[0] and len(closing.group(1)) >= len(fence):
                fence = None
                kinds.append("close")
            else:
                kinds.append("code")
            continue
        opening = FENCE_OPEN.match(raw)
        if opening and not (opening.group(1)[0] == "`" and "`" in opening.group(2)):
            fence = opening.group(1)
            kinds.append("code")
            continue
        kinds.append("text")
    return lines, kinds


def stamp_section(lines: list[str], kinds: list[str], defaults: dict) -> tuple[int, int] | None:
    """Locate the single existing stamp section as [heading, end) line indexes.

    A section ends at the next heading of the same or higher level, or at EOF.
    More than one stamp heading always fails closed.
    """
    heading = defaults.get("stamp_heading", "## Governance")
    wanted = atx_heading(heading)
    if wanted is None or "\n" in heading or "\r" in heading:
        raise ValueError("stamp_heading must be a single ATX heading line")
    headings = [(i, *atx_heading(line)) for i, line in enumerate(lines)
                if kinds[i] == "text" and atx_heading(line)]
    matches = [i for i, level, text in headings if (level, text) == wanted]
    if len(matches) > 1:
        raise ValueError(f"stamp heading {heading!r} appears {len(matches)} times; "
                         "refusing to choose or add a governance section (fail closed)")
    if not matches:
        return None
    start = matches[0]
    return start, next((i for i, level, _ in headings if i > start and level <= wanted[0]), len(lines))


def complete_stamp(lines: list[str], kinds: list[str], section: tuple[int, int], asset: dict,
                   fallback_newline: str) -> tuple[str, list[str]]:
    """Add only the missing marker lines at the end of the one existing stamp section.

    Every original byte is kept in order; the only change is one contiguous insertion
    after the section's last nonblank line. Ambiguous boundaries fail closed.
    """
    start, end = section
    text = "".join(lines[start:end])
    missing = [line for markers, line in stamp_lines(asset) if not all(m in text for m in markers)]
    if not missing:
        return "".join(lines), []
    for i in range(start + 1, end):
        if (kinds[i] == "text" and kinds[i - 1] == "text" and lines[i - 1].strip()
                and SETEXT_UNDERLINE.match(lines[i].rstrip("\r\n")) and not atx_heading(lines[i - 1])):
            raise ValueError(f"stamp section boundary is ambiguous (possible setext heading at body line {i + 1}); fail closed")
    last = max(i for i in range(start, end) if lines[i].strip())
    if kinds[last] == "code":
        raise ValueError("stamp section ends inside an unclosed fenced code block; fail closed")
    ending = re.search(r"\r?\n\Z", lines[last])
    newline = ending.group(0) if ending else fallback_newline
    block = missing if last != start and LIST_ITEM.match(lines[last]) else ["", *missing]
    insert = "".join(item + newline for item in block) if ending else "".join(newline + item for item in block)
    return "".join(lines[:last + 1]) + insert + "".join(lines[last + 1:]), missing


def load_config(config: str, bodies_dir: str, only: str) -> tuple[dict, list, dict]:
    raw = Path(config).read_bytes().decode("utf-8")
    cfg = json.loads(raw)
    if cfg.get("schema") != "szl.governance.hf_card_expectations/v1":
        raise ValueError("unexpected expectation schema")
    defaults = cfg.get("defaults", {})
    if defaults.get("org") != ORG:
        raise ValueError("expectation must declare SZLHOLDINGS")
    assets = cfg.get("assets")
    if not isinstance(assets, list) or not assets:
        raise ValueError("no assets declared")
    seen, bodies = set(), {}
    root = Path(bodies_dir).resolve()
    for asset in assets:
        if not isinstance(asset, dict):
            raise ValueError("asset must be an object")
        repo_id = asset.get("repo_id", "")
        if not isinstance(repo_id, str) or not re.fullmatch(r"SZLHOLDINGS/[A-Za-z0-9][A-Za-z0-9_.-]*", repo_id):
            raise ValueError("invalid or out-of-namespace repository")
        if repo_id in seen:
            raise ValueError(f"duplicate asset: {repo_id}")
        seen.add(repo_id)
        if asset.get("kind") not in ("spaces", "datasets", "models"):
            raise ValueError(f"invalid kind: {repo_id}")
        if asset["kind"] == "spaces" and "short_description" in asset:
            description = asset["short_description"]
            if not isinstance(description, str) or not 1 <= len(description) <= 60:
                raise ValueError(f"Space short_description must contain 1 to 60 characters: {repo_id}")
        if not re.fullmatch(r"szl-holdings/[A-Za-z0-9][A-Za-z0-9_.-]*", asset.get("source_repo", "")):
            raise ValueError(f"invalid source repository: {repo_id}")
        for key in ("license", "title", "short_description"):
            value = asset.get(key, defaults.get(key) if key == "license" else None)
            if value is not None and (not isinstance(value, str) or not value or "\n" in value or "\r" in value):
                raise ValueError(f"invalid declared scalar: {repo_id}/{key}")
        body_file = asset.get("body_file")
        if body_file:
            path = (root / body_file).resolve()
            if not path.is_relative_to(root) or not path.is_file():
                raise ValueError(f"missing or outside body file: {repo_id}")
            bodies[body_file] = digest(path.read_bytes().decode("utf-8"))
    wanted = {item.strip() for item in only.split(",") if item.strip()}
    if only and not wanted:
        raise ValueError("empty target selection")
    if wanted - seen:
        raise ValueError("unknown target selection: " + ", ".join(sorted(wanted - seen)))
    selected = [a for a in assets if not wanted or a["repo_id"] in wanted]
    if not selected:
        raise ValueError("no selected assets")
    return cfg, selected, {"config_sha256": digest(raw), "body_files_sha256": bodies}


def plan_asset(asset: dict, defaults: dict, token: str | None, bodies_dir: str,
               allow_body: bool) -> dict:
    repo_id, kind = asset["repo_id"], asset["kind"]
    row = {"repo_id": repo_id, "kind": kind, "label": MEASURED, "changes": [],
           "reason": asset.get("reason", "")}
    detail, status = hub_request("GET", f"/api/{kind}/{repo_id}", token)
    row["read_status"] = status
    try:
        if status != 200:
            raise ValueError(f"repository read HTTP {status}")
        revision = json.loads(detail).get("sha", "")
        if not isinstance(revision, str) or not SHA.fullmatch(revision):
            raise ValueError("repository returned no exact revision")
        row["hub_revision"] = revision
        seg = "" if kind == "models" else kind + "/"
        text, status = hub_request("GET", f"/{seg}{repo_id}/raw/{revision}/README.md", token)
        row["read_status"] = status
        if status != 200:
            raise ValueError(f"card read HTTP {status}")
        prefix, fm, closing, body = split_card(text)
        for key in ("license", "title", "short_description"):
            want = asset.get(key, defaults.get("license") if key == "license" else None)
            if want is not None:
                fm, changed = set_scalar(fm, key, want)
                if changed:
                    row["changes"].append(f"front_matter.{key}={want}")
        body_file = asset.get("body_file")
        if body_file and allow_body:
            desired = (Path(bodies_dir) / body_file).read_bytes().decode("utf-8")
            desired = ("\r\n" if prefix.endswith("\r\n") else "\n") + desired
            if body != desired:
                body = desired
                row["changes"].append(f"body<={body_file}")
        if asset.get("require_stamp", defaults.get("require_stamp", True)):
            newline = "\r\n" if prefix.endswith("\r\n") else "\n"
            lines, kinds = markdown_lines(body)
            # Duplicate stamp headings fail closed even when every marker is present.
            section = stamp_section(lines, kinds, defaults)
            if not has_stamp(body, asset, defaults):
                if section is None:
                    separator = "" if body.endswith(newline * 2) else newline if body.endswith(newline) else newline * 2
                    body += separator + stamp_block(asset, defaults, newline)
                    row["changes"].append("body+=governance_stamp")
                else:
                    body, added = complete_stamp(lines, kinds, section, asset, newline)
                    if added:
                        row["changes"].append("governance_stamp~=completed_missing_markers")
                        row["governance_markers_added"] = added
        new_text = prefix + fm + closing + body
        if new_text == text:
            row["changes"] = []
        row.update(before_sha256=digest(text), after_sha256=digest(new_text),
                   bytes_before=len(text.encode("utf-8")), bytes_after=len(new_text.encode("utf-8")),
                   original_text=text, new_text=new_text)
        return row
    except (ValueError, OSError, TypeError, AttributeError) as exc:
        row.update(label=UNAVAILABLE, detail=str(exc))
        return row


def identity_preflight(token: str, expected_owner: str) -> dict:
    detail, status = hub_request("GET", "/api/whoami-v2", token)
    result = {"label": UNAVAILABLE, "http_status": status}
    if status != 200:
        result["detail"] = f"identity preflight HTTP {status}"
        return result
    try:
        identity = json.loads(detail)
        name = identity.get("name")
        role = next((org.get("roleInOrg") for org in identity.get("orgs", []) if org.get("name") == ORG), None)
        result.update(name=name, organization=ORG, role=role)
        if name != expected_owner:
            result["detail"] = "credential owner does not match expected owner"
        elif role not in ("admin", "write", "contributor"):
            result["detail"] = "credential owner lacks an eligible organization role"
        elif identity.get("auth", {}).get("accessToken", {}).get("role") == "read":
            result["detail"] = "credential is explicitly read-only"
        else:
            result["label"] = MEASURED
    except (ValueError, TypeError, AttributeError):
        result["detail"] = "identity response is malformed"
    return result


def oidc_resource(asset: dict) -> str:
    """Trusted Publisher resource: namespace/name for models, kind/namespace/name otherwise."""
    return asset["repo_id"] if asset["kind"] == "models" else f"{asset['kind']}/{asset['repo_id']}"


def oidc_env_name(resource: str) -> str:
    return OIDC_ENV_PREFIX + re.sub(r"[^A-Z0-9]", "_", resource.upper())


def oidc_targets(assets: list) -> list[dict]:
    """One resource and one credential variable per selected asset; name collisions fail closed."""
    targets, seen = [], {}
    for asset in assets:
        resource = oidc_resource(asset)
        env = oidc_env_name(resource)
        if env in seen:
            raise ValueError(f"OIDC credential variable {env} is ambiguous: {seen[env]} and {asset['repo_id']}")
        seen[env] = asset["repo_id"]
        targets.append({"repo_id": asset["repo_id"], "kind": asset["kind"], "resource": resource, "env": env})
    return targets


def oidc_credentials(targets: list, environ) -> dict[str, str]:
    """Bind each target to its own exchanged token. Nothing is shared or substituted."""
    missing = [t for t in targets if not environ.get(t["env"])]
    if missing:
        raise ValueError("--auth oidc requires a Trusted Publisher token for every selected target; missing: "
                         + ", ".join(f"{t['repo_id']} ({t['resource']} via {t['env']})" for t in missing))
    malformed = [t for t in targets if not HUB_TOKEN_SHAPE.fullmatch(environ[t["env"]])]
    if malformed:
        raise ValueError("Trusted Publisher token is not a single Hub token: "
                         + ", ".join(f"{t['repo_id']} ({t['env']})" for t in malformed))
    return {t["repo_id"]: environ[t["env"]] for t in targets}


def oidc_preflight(targets: list, tokens: dict) -> dict:
    """Prove write access per target with the Hub auth check, not an owner or role.

    Exchanged Trusted Publisher tokens act as a synthetic [OIDC] user, so the
    whoami-v2 owner/role contract of token mode does not apply. The whoami-v2
    answer is kept as REPORTED context only and never gates a write.
    """
    rows = []
    for target in targets:
        token = tokens[target["repo_id"]]
        _, status = hub_request("GET", f"/api/{target['kind']}/{target['repo_id']}/auth-check/write", token)
        row = {"repo_id": target["repo_id"], "resource": target["resource"], "check": "auth-check/write",
               "http_status": status, "label": MEASURED if status == 200 else UNAVAILABLE}
        if status != 200:
            row["detail"] = f"write auth check HTTP {status}"
        detail, whoami_status = hub_request("GET", "/api/whoami-v2", token)
        whoami = {"label": REPORTED, "http_status": whoami_status}
        if whoami_status == 200:
            try:
                identity = json.loads(detail)
                whoami.update(name=identity.get("name"), type=identity.get("type"),
                              token_role=identity.get("auth", {}).get("accessToken", {}).get("role"))
            except (ValueError, TypeError, AttributeError):
                whoami["detail"] = "identity response is malformed"
        row["whoami"] = whoami
        rows.append(row)
    failed = [row for row in rows if row["label"] != MEASURED]
    result = {"mode": "oidc", "label": UNAVAILABLE if failed else MEASURED, "targets": rows}
    if failed:
        result["detail"] = "Trusted Publisher write check failed: " + ", ".join(
            f"{row['repo_id']} HTTP {row['http_status']}" for row in failed)
    return result


def redact(text: str, secrets) -> str:
    for secret in sorted({s for s in secrets if s}, key=len, reverse=True):
        text = text.replace(secret, "[REDACTED]")
    return text


def list_oidc_targets(args) -> int:
    """Print env name, resource and repo per selected target. No network, no receipt."""
    try:
        _, assets, _ = load_config(args.config, args.bodies_dir, args.only)
        targets = oidc_targets(assets)
    except (ValueError, OSError, TypeError, KeyError, AttributeError) as exc:
        print("FATAL: " + str(exc), file=sys.stderr)
        return 1
    for target in targets:
        print("\t".join((target["env"], target["resource"], target["repo_id"])))
    return 0


def apply_asset(row: dict, token: str, message: str, prefer_pr: bool = False) -> dict:
    if not row["changes"]:
        row.update(applied=False, apply_route="none", outcome="already_current", verified=True)
        return row
    header = {"key": "header", "value": {"summary": message, "parentCommit": row["hub_revision"]}}
    file_record = {"key": "file", "value": {"path": "README.md", "encoding": "base64",
        "content": base64.b64encode(row["new_text"].encode("utf-8")).decode("ascii")}}
    body = (json.dumps(header) + "\n" + json.dumps(file_record) + "\n").encode("utf-8")
    base = f"/api/{row['kind']}/{row['repo_id']}/commit/main"
    routes = [("pull_request", base + "?create_pr=1")] if prefer_pr else [("main", base), ("pull_request", base + "?create_pr=1")]
    row["apply_attempts"] = []
    for route, path in routes:
        detail, status = hub_request("POST", path, token, body, "application/x-ndjson")
        row["apply_attempts"].append({"route": route, "http_status": status})
        row.update(apply_status=status, apply_route=route)
        if status in (200, 201):
            try:
                response = json.loads(detail)
                commit = response.get("commitOid", "")
                if not isinstance(commit, str) or not SHA.fullmatch(commit):
                    raise ValueError("missing commit revision")
                if route == "pull_request" and not response.get("pullRequestUrl"):
                    raise ValueError("missing pull request URL")
            except (ValueError, TypeError, AttributeError):
                row.update(applied=False, verified=False, outcome="unknown_write_result",
                           detail="successful write response lacks commit or pull request identity; inspect Hub before retry")
                return row
            row.update(applied=True, commit_oid=commit, commit_url=response.get("commitUrl"),
                       pull_request_url=response.get("pullRequestUrl"), main_verified=False,
                       outcome="pull_request_created" if route == "pull_request" else "committed")
            if route == "pull_request":
                row["pending_main_readback"] = True
            seg = "" if row["kind"] == "models" else row["kind"] + "/"
            actual, read_status = hub_request("GET", f"/{seg}{row['repo_id']}/raw/{commit}/README.md", token)
            row["verification_status"] = read_status
            row["verified"] = read_status == 200 and digest(actual) == row["after_sha256"]
            if not row["verified"]:
                row["detail"] = "committed card could not be verified against planned bytes"
            elif route == "main":
                main, main_status = hub_request("GET", f"/api/{row['kind']}/{row['repo_id']}", token)
                try:
                    main_revision = json.loads(main).get("sha", "") if main_status == 200 else ""
                except (ValueError, TypeError, AttributeError):
                    main_revision = ""
                row["main_revision"] = main_revision
                row["main_read_status"] = main_status
                row["main_verified"] = main_revision == commit
                row["verified"] = row["main_verified"]
                if not row["verified"]:
                    row["detail"] = "main revision could not be verified as the committed card revision"
            return row
        if status != 403:
            break
    row.update(applied=False, verified=False, detail=f"card write HTTP {row['apply_status']}",
               outcome="unknown_write_result" if row["apply_status"] == 0 or row["apply_status"] >= 500 else "write_failed")
    return row


def validate_expected_plan(payload: dict, path: str) -> None:
    plan = json.loads(Path(path).read_bytes().decode("utf-8"))
    if plan.get("schema") != SCHEMA or plan.get("mode") != "plan" or plan.get("success") is not True:
        raise ValueError("expected plan is not a successful plan receipt")
    for key in ("source_revision", "config_sha256", "body_files_sha256", "body_replace_allowed"):
        if plan.get(key) != payload.get(key):
            raise ValueError(f"expected plan differs: {key}")
    if not SHA.fullmatch(payload.get("source_revision", "")):
        raise ValueError("expected-plan apply requires an exact source revision")
    planned, actual = plan.get("assets", []), payload["assets"]
    if len(planned) != len(actual) or {r["repo_id"] for r in planned} != {r["repo_id"] for r in actual}:
        raise ValueError("expected plan target set differs")
    indexed = {r["repo_id"]: r for r in planned}
    if len(indexed) != len(planned):
        raise ValueError("expected plan has duplicate assets")
    for row in actual:
        expected = indexed[row["repo_id"]]
        if expected.get("label") != MEASURED or row["label"] != MEASURED:
            raise ValueError("expected plan contains an unavailable target")
        for key in ("kind", "hub_revision", "before_sha256", "after_sha256", "changes", "new_text"):
            if expected.get(key) != row.get(key):
                raise ValueError(f"expected plan differs: {row['repo_id']}/{key}")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", default=".github/config/hf_card_expectations.json")
    parser.add_argument("--bodies-dir", default=".github/config/hf_cards")
    parser.add_argument("--out-json", default="reports/governance/hf-card-reconcile.json")
    parser.add_argument("--only", default="")
    parser.add_argument("--apply", action="store_true")
    parser.add_argument("--allow-body-replace", action="store_true")
    parser.add_argument("--prefer-pr", action="store_true")
    parser.add_argument("--expected-plan")
    parser.add_argument("--expected-owner", default="betterwithage")
    parser.add_argument("--message", default="chore(card): reconcile governed card metadata")
    parser.add_argument("--auth", choices=("token", "oidc"), default="token",
                        help="apply credential: token = first nonempty TOKEN_KEYS secret for every target; "
                             "oidc = one Trusted Publisher token per target from HF_OIDC_TOKEN_<RESOURCE>")
    parser.add_argument("--list-oidc-targets", action="store_true",
                        help="print each selected target's credential variable, OIDC resource and repo, then exit")
    args = parser.parse_args()
    if args.list_oidc_targets:
        return list_oidc_targets(args)
    payload = {"schema": SCHEMA, "generated_at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
               "source_revision": os.environ.get("GITHUB_SHA", ""), "mode": "apply" if args.apply else "plan",
               "body_replace_allowed": args.allow_body_replace, "assets": [], "receipt_state": "UNSIGNED_HONEST"}
    # Token mode keeps the original precedence; OIDC mode never reads a long-lived secret.
    source = None if args.auth == "oidc" else next((key for key in TOKEN_KEYS if os.environ.get(key)), None)
    token = os.environ[source] if source else None
    tokens: dict[str, str] = {}
    if args.apply:
        payload["auth"] = {"mode": args.auth, "token_recorded": False}
        if args.auth == "token":
            payload["auth"]["source"] = source
    code = 1
    try:
        if args.apply and not args.expected_plan:
            raise ValueError("--apply requires --expected-plan")
        if args.auth == "oidc" and not args.apply:
            raise ValueError("--auth oidc is only valid with --apply; plans read anonymously")
        cfg, assets, hashes = load_config(args.config, args.bodies_dir, args.only)
        payload.update(hashes)
        if args.expected_plan and not args.apply:
            raise ValueError("--expected-plan is only valid with --apply")
        if args.apply and args.auth == "oidc":
            targets = oidc_targets(assets)
            payload["auth"]["targets"] = [{"repo_id": t["repo_id"], "resource": t["resource"]} for t in targets]
            tokens = oidc_credentials(targets, os.environ)
            payload["identity"] = oidc_preflight(targets, tokens)
        elif args.apply:
            if not token:
                raise ValueError("--apply requires an HF token")
            tokens = {asset["repo_id"]: token for asset in assets}
            payload["identity"] = identity_preflight(token, args.expected_owner)
        if args.apply and payload["identity"]["label"] != MEASURED:
            raise ValueError(payload["identity"].get("detail", "identity preflight failed"))
        payload["assets"] = [plan_asset(asset, cfg["defaults"], tokens.get(asset["repo_id"], token), args.bodies_dir,
                                        args.allow_body_replace) for asset in assets]
        if not payload["assets"] or any(row["label"] != MEASURED for row in payload["assets"]):
            raise ValueError("one or more selected cards could not be planned: " + "; ".join(
                f"{row['repo_id']}: {row.get('detail', 'unknown')}" for row in payload["assets"] if row["label"] != MEASURED))
        if args.expected_plan:
            validate_expected_plan(payload, args.expected_plan)
        if args.apply:
            for row in payload["assets"]:
                apply_asset(row, tokens[row["repo_id"]], args.message, args.prefer_pr)
            code = 0 if all(row.get("verified") for row in payload["assets"]) else 1
        else:
            code = 0
    except (ValueError, OSError, TypeError, KeyError, AttributeError) as exc:
        present = [value for key, value in os.environ.items() if key in TOKEN_KEYS or key.startswith(OIDC_ENV_PREFIX)]
        payload["error"] = redact(str(exc), [token, *tokens.values(), *present])
    payload["success"] = code == 0
    output = Path(args.out_json)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_bytes((json.dumps(payload, indent=2, sort_keys=True, ensure_ascii=False) + "\n").encode("utf-8"))
    for row in payload["assets"]:
        print(f"{row['repo_id']}: {row['label']} changes={row['changes']} applied={row.get('applied', 'plan-only')}")
    if payload.get("error"):
        print("FATAL: " + payload["error"], file=sys.stderr)
    return code


if __name__ == "__main__":
    raise SystemExit(main())
