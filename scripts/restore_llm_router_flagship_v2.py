#!/usr/bin/env python3
"""Restore and attest the SZL LLM Router flagship, revision for revision.

GitHub is the source authority. Hugging Face is the public runtime mirror.
A11oy is the integrated product view. This controller never creates a duplicate
repository or Space and never records a credential value.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import shutil
import ssl
import tempfile
import time
import urllib.error
import urllib.parse
import urllib.request
import zipfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable, Mapping

GITHUB_API = "https://api.github.com"
SOURCE_REPOSITORY = "szl-holdings/szl-router"
SOURCE_BRANCH = "main"
HF_SPACE = "SZLHOLDINGS/llm-router-live"
HF_ORG_CARD = "SZLHOLDINGS/README"
BEGIN = "<!-- SZL_LLM_ROUTER_FLAGSHIP:BEGIN -->"
END = "<!-- SZL_LLM_ROUTER_FLAGSHIP:END -->"
USER_AGENT = "szl-llm-router-flagship-restorer-v2/1.0"
SHA40 = re.compile(r"^[0-9a-f]{40}$")
MAX_SOURCE_ARCHIVE = 80 * 1024 * 1024
MAX_HTTP_BODY = 4 * 1024 * 1024
TERMINAL_FAILURES = {"BUILD_ERROR", "RUNTIME_ERROR", "CONFIG_ERROR", "NO_APP_FILE"}


class RestoreError(RuntimeError):
    pass


def utcnow() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def sha256_bytes(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def required_env(name: str) -> str:
    value = os.environ.get(name, "").strip()
    if not value:
        raise RestoreError(f"required environment variable {name} is absent")
    return value


def github_json(
    token: str,
    method: str,
    path: str,
    *,
    payload: Mapping[str, Any] | None = None,
    expected: Iterable[int] = (200,),
) -> Any:
    body = None
    headers = {
        "Accept": "application/vnd.github+json",
        "Authorization": f"Bearer {token}",
        "User-Agent": USER_AGENT,
        "X-GitHub-Api-Version": "2022-11-28",
    }
    if payload is not None:
        body = json.dumps(payload, separators=(",", ":")).encode("utf-8")
        headers["Content-Type"] = "application/json"
    request = urllib.request.Request(
        GITHUB_API + path,
        method=method,
        headers=headers,
        data=body,
    )
    try:
        with urllib.request.urlopen(
            request,
            timeout=45,
            context=ssl.create_default_context(),
        ) as response:
            raw = response.read(MAX_HTTP_BODY + 1)
            if len(raw) > MAX_HTTP_BODY:
                raise RestoreError("bounded GitHub response limit exceeded")
            if response.status not in set(expected):
                raise RestoreError(
                    f"GitHub returned unexpected HTTP {response.status} for {method} {path}"
                )
    except urllib.error.HTTPError as exc:
        raise RestoreError(f"GitHub returned HTTP {exc.code} for {method} {path}") from exc
    except (urllib.error.URLError, TimeoutError, OSError) as exc:
        raise RestoreError(f"GitHub transport failed for {method} {path}") from exc
    if not raw:
        return None
    try:
        return json.loads(raw)
    except json.JSONDecodeError as exc:
        raise RestoreError(f"GitHub returned malformed JSON for {method} {path}") from exc


def download_source_archive(token: str, revision: str, destination: Path) -> None:
    request = urllib.request.Request(
        f"{GITHUB_API}/repos/{SOURCE_REPOSITORY}/zipball/{revision}",
        headers={
            "Accept": "application/vnd.github+json",
            "Authorization": f"Bearer {token}",
            "User-Agent": USER_AGENT,
            "X-GitHub-Api-Version": "2022-11-28",
        },
    )
    try:
        with urllib.request.urlopen(
            request,
            timeout=90,
            context=ssl.create_default_context(),
        ) as response:
            raw = response.read(MAX_SOURCE_ARCHIVE + 1)
    except (urllib.error.HTTPError, urllib.error.URLError, TimeoutError, OSError) as exc:
        raise RestoreError("exact GitHub source archive could not be downloaded") from exc
    if len(raw) > MAX_SOURCE_ARCHIVE:
        raise RestoreError("exact GitHub source archive exceeded the bounded size")
    destination.write_bytes(raw)


def safe_extract(archive: Path, destination: Path) -> Path:
    with zipfile.ZipFile(archive) as bundle:
        roots: set[str] = set()
        for member in bundle.infolist():
            path = Path(member.filename)
            if path.is_absolute() or ".." in path.parts:
                raise RestoreError("source archive contains an unsafe path")
            if path.parts:
                roots.add(path.parts[0])
        if len(roots) != 1:
            raise RestoreError("source archive must contain exactly one root directory")
        bundle.extractall(destination)
    return destination / next(iter(roots))


def replace_frontmatter(readme: Path, revision: str) -> None:
    original = readme.read_text(encoding="utf-8") if readme.exists() else ""
    required = {
        "title": "SZL LLM Router",
        "emoji": "🧭",
        "colorFrom": "indigo",
        "colorTo": "cyan",
        "sdk": "docker",
        "app_port": "8000",
        "pinned": "false",
        "license": "apache-2.0",
        "short_description": "Flagship sovereign-first LLM routing with verifiable receipts",
    }
    body = original
    present: dict[str, str] = {}
    extras: list[str] = []
    if original.startswith("---\n"):
        closing = original.find("\n---\n", 4)
        if closing >= 0:
            for line in original[4:closing].splitlines():
                if ":" not in line:
                    extras.append(line)
                    continue
                key, value = line.split(":", 1)
                if key.strip() in required:
                    present[key.strip()] = value.strip()
                else:
                    extras.append(line)
            body = original[closing + 5 :].lstrip("\n")
    lines = [f"{key}: {value}" for key, value in required.items()]
    lines.extend(line for line in extras if line.strip())
    notice = (
        f"<!-- exact_source: {SOURCE_REPOSITORY}@{revision} -->\n"
        "<!-- classification: FLAGSHIP; provider readiness is independently observed -->\n"
    )
    body = re.sub(
        r"<!-- exact_source: .*? -->\n(?:<!-- classification: .*? -->\n)?",
        "",
        body,
        count=1,
    ).lstrip("\n")
    rendered = "---\n" + "\n".join(lines) + "\n---\n\n" + notice + "\n" + body
    readme.write_text(rendered, encoding="utf-8", newline="\n")


def insert_card(existing: str, block: str) -> str:
    block = block.strip() + "\n"
    if BEGIN not in block or END not in block:
        raise RestoreError("router card source is missing its idempotency markers")
    if BEGIN in existing and END in existing:
        return re.sub(
            re.escape(BEGIN) + r".*?" + re.escape(END) + r"\n?",
            block,
            existing,
            count=1,
            flags=re.DOTALL,
        )
    if existing.startswith("---\n"):
        closing = existing.find("\n---\n", 4)
        if closing >= 0:
            at = closing + 5
            return existing[:at] + "\n\n" + block + "\n" + existing[at:].lstrip("\n")
    return block + "\n" + existing


def hf_attr(value: Any, name: str, default: Any = None) -> Any:
    direct = getattr(value, name, default)
    if direct is not default:
        return direct
    raw = getattr(value, "raw", None)
    if isinstance(raw, Mapping):
        return raw.get(name, default)
    return default


def public_json(url: str) -> Mapping[str, Any]:
    request = urllib.request.Request(
        url,
        headers={"User-Agent": USER_AGENT, "Accept": "application/json"},
    )
    try:
        with urllib.request.urlopen(
            request,
            timeout=30,
            context=ssl.create_default_context(),
        ) as response:
            if response.status != 200:
                raise RestoreError(f"public API returned HTTP {response.status}")
            raw = response.read(MAX_HTTP_BODY + 1)
    except (urllib.error.HTTPError, urllib.error.URLError, TimeoutError, OSError) as exc:
        raise RestoreError(f"public API could not be verified: {url}") from exc
    if len(raw) > MAX_HTTP_BODY:
        raise RestoreError("public API response exceeded the bounded size")
    try:
        value = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise RestoreError("public API returned malformed JSON") from exc
    if not isinstance(value, Mapping):
        raise RestoreError("public API returned a non-object")
    return value


def public_html(url: str) -> tuple[int, bytes]:
    request = urllib.request.Request(
        url,
        headers={"User-Agent": USER_AGENT, "Accept": "text/html"},
    )
    try:
        with urllib.request.urlopen(
            request,
            timeout=30,
            context=ssl.create_default_context(),
        ) as response:
            raw = response.read(MAX_HTTP_BODY + 1)
            status = int(response.status)
    except (urllib.error.HTTPError, urllib.error.URLError, TimeoutError, OSError) as exc:
        raise RestoreError(f"public product surface could not be verified: {url}") from exc
    if status != 200 or len(raw) > MAX_HTTP_BODY:
        raise RestoreError(f"public product surface was not a bounded HTTP 200: {url}")
    return status, raw


def validate_contract(manifest_path: Path, card_path: Path) -> None:
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    assert manifest["classification"] == "FLAGSHIP"
    assert manifest["github_source"]["repository"] == SOURCE_REPOSITORY
    assert manifest["github_source"]["must_be_archived"] is False
    assert manifest["hugging_face_runtime"]["repository"] == HF_SPACE
    assert manifest["hugging_face_runtime"]["must_be_private"] is False
    assert manifest["runtime_contract"]["provider_keys_committed"] is False
    card = card_path.read_text(encoding="utf-8")
    assert BEGIN in card and END in card
    assert SOURCE_REPOSITORY in card
    assert HF_SPACE in card
    assert "Conjecture 1" in card


def restore(manifest_path: Path, card_path: Path, receipt_path: Path, wait_seconds: int) -> dict[str, Any]:
    github_token = required_env("ROUTER_GH_TOKEN")
    hf_token = required_env("HF_TOKEN")

    receipt: dict[str, Any] = {
        "schema": "szl.llm-router-flagship-restoration/v2",
        "started_at": utcnow(),
        "source_authority": SOURCE_REPOSITORY,
        "runtime_mirror": HF_SPACE,
        "manifest_sha256": sha256_bytes(manifest_path.read_bytes()),
        "card_sha256": sha256_bytes(card_path.read_bytes()),
        "credentials_recorded": False,
        "authorization_proof": False,
        "complete": False,
    }

    repository = github_json(
        github_token,
        "PATCH",
        f"/repos/{SOURCE_REPOSITORY}",
        payload={
            "archived": False,
            "description": (
                "FLAGSHIP: sovereign-first OpenAI-compatible LLM router with "
                "verifiable routing receipts; source for SZLHOLDINGS/llm-router-live"
            ),
            "homepage": "https://a-11-oy.com/code",
            "has_issues": True,
        },
    )
    if not isinstance(repository, Mapping) or repository.get("archived") is not False:
        raise RestoreError("GitHub did not confirm the router repository as unarchived")
    github_json(
        github_token,
        "PUT",
        f"/repos/{SOURCE_REPOSITORY}/topics",
        payload={
            "names": [
                "flagship",
                "llm-router",
                "openai-compatible",
                "sovereign-ai",
                "governed-inference",
                "routing-receipts",
                "provider-failover",
                "szl-holdings",
            ]
        },
    )
    branch = github_json(
        github_token,
        "GET",
        f"/repos/{SOURCE_REPOSITORY}/branches/{SOURCE_BRANCH}",
    )
    revision = str((branch.get("commit") or {}).get("sha") if isinstance(branch, Mapping) else "")
    if not SHA40.fullmatch(revision):
        raise RestoreError("GitHub source branch did not return an exact revision")
    receipt["github"] = {
        "archived": False,
        "source_revision": revision,
        "description": repository.get("description"),
        "homepage": repository.get("homepage"),
    }

    try:
        from huggingface_hub import HfApi, hf_hub_download
        from huggingface_hub.errors import RepositoryNotFoundError
    except ImportError as exc:
        raise RestoreError("huggingface_hub is unavailable") from exc

    api = HfApi(token=hf_token)
    try:
        before = api.repo_info(repo_id=HF_SPACE, repo_type="space", token=hf_token)
    except RepositoryNotFoundError as exc:
        raise RestoreError("existing router Space is inaccessible; no duplicate was created") from exc

    with tempfile.TemporaryDirectory(prefix="szl-router-v2-") as temporary:
        temp = Path(temporary)
        archive = temp / "source.zip"
        extracted = temp / "source"
        extracted.mkdir()
        download_source_archive(github_token, revision, archive)
        root = safe_extract(archive, extracted)
        source_space = root / "space"
        if not source_space.is_dir():
            raise RestoreError("canonical router source does not contain space/")
        stage = temp / "stage"
        shutil.copytree(source_space, stage)
        replace_frontmatter(stage / "README.md", revision)
        (stage / "source_revision.txt").write_text(revision + "\n", encoding="ascii")
        provenance = {
            "schema": "szl.space-provenance/v2",
            "classification": "FLAGSHIP",
            "github_repository": SOURCE_REPOSITORY,
            "github_revision": revision,
            "hugging_face_repository": HF_SPACE,
            "generated_at": utcnow(),
            "credential_values_embedded": False,
            "model_provider_readiness_inferred": False,
            "authority_created": False,
        }
        (stage / "SPACE_PROVENANCE.json").write_text(
            json.dumps(provenance, indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )

        api.update_repo_settings(repo_id=HF_SPACE, repo_type="space", private=False, token=hf_token)
        commit = api.upload_folder(
            repo_id=HF_SPACE,
            repo_type="space",
            folder_path=str(stage),
            path_in_repo=".",
            commit_message=f"Restore exact flagship source {revision}",
            token=hf_token,
        )
        api.restart_space(repo_id=HF_SPACE, token=hf_token)

        deadline = time.monotonic() + wait_seconds
        stage_name = "UNKNOWN"
        hub_revision = None
        runtime_revision = None
        while time.monotonic() < deadline:
            info = api.repo_info(repo_id=HF_SPACE, repo_type="space", token=hf_token)
            runtime = api.get_space_runtime(repo_id=HF_SPACE, token=hf_token)
            hub_revision = str(hf_attr(info, "sha", "") or "")
            stage_name = str(hf_attr(runtime, "stage", "UNKNOWN") or "UNKNOWN").upper()
            runtime_revision = str(hf_attr(runtime, "sha", "") or "") or None
            exact_runtime = not runtime_revision or runtime_revision == hub_revision
            if stage_name == "RUNNING" and hub_revision and exact_runtime:
                break
            if stage_name in TERMINAL_FAILURES:
                raise RestoreError(f"router Space entered terminal stage {stage_name}")
            time.sleep(15)
        else:
            raise RestoreError(
                f"router Space did not converge to exact RUNNING state; last stage={stage_name}"
            )

        remote_source = Path(
            hf_hub_download(
                repo_id=HF_SPACE,
                repo_type="space",
                revision=hub_revision,
                filename="source_revision.txt",
                token=hf_token,
            )
        ).read_text(encoding="ascii").strip()
        if remote_source != revision:
            raise RestoreError("published source_revision.txt does not match GitHub source")
        remote_provenance = json.loads(
            Path(
                hf_hub_download(
                    repo_id=HF_SPACE,
                    repo_type="space",
                    revision=hub_revision,
                    filename="SPACE_PROVENANCE.json",
                    token=hf_token,
                )
            ).read_text(encoding="utf-8")
        )
        if remote_provenance.get("github_revision") != revision:
            raise RestoreError("published provenance does not match GitHub source")

        public_info = public_json("https://huggingface.co/api/spaces/SZLHOLDINGS/llm-router-live")
        if public_info.get("private") is not False:
            raise RestoreError("public Hub API still reports the router Space as private")
        public_sha = str(public_info.get("sha") or "")
        if public_sha and public_sha != hub_revision:
            raise RestoreError("public Hub API revision does not match authenticated revision")

        org_type = None
        org_readme = ""
        for candidate in ("space", "dataset", "model"):
            try:
                api.repo_info(repo_id=HF_ORG_CARD, repo_type=candidate, token=hf_token)
                org_type = candidate
                try:
                    local = hf_hub_download(
                        repo_id=HF_ORG_CARD,
                        repo_type=candidate,
                        filename="README.md",
                        token=hf_token,
                    )
                    org_readme = Path(local).read_text(encoding="utf-8")
                except Exception:
                    org_readme = ""
                break
            except Exception:
                continue
        if org_type is None:
            raise RestoreError("Hugging Face organization-card repository was not found")
        rendered = insert_card(org_readme, card_path.read_text(encoding="utf-8"))
        card_commit = api.upload_file(
            repo_id=HF_ORG_CARD,
            repo_type=org_type,
            path_or_fileobj=rendered.encode("utf-8"),
            path_in_repo="README.md",
            commit_message=f"Showcase SZL LLM Router flagship at {revision[:12]}",
            token=hf_token,
        )
        reread = Path(
            hf_hub_download(
                repo_id=HF_ORG_CARD,
                repo_type=org_type,
                filename="README.md",
                force_download=True,
                token=hf_token,
            )
        ).read_text(encoding="utf-8")
        if BEGIN not in reread or END not in reread or SOURCE_REPOSITORY not in reread:
            raise RestoreError("Hugging Face organization card did not retain the flagship block")

        product_status, product_body = public_html("https://a-11-oy.com/code")
        receipt["hugging_face"] = {
            "space": HF_SPACE,
            "private": False,
            "stage": stage_name,
            "repository_revision": hub_revision,
            "runtime_revision": runtime_revision,
            "public_api_revision": public_sha or None,
            "exact_source_revision": remote_source,
            "provenance_sha256": sha256_bytes(
                json.dumps(remote_provenance, sort_keys=True, separators=(",", ":")).encode("utf-8")
            ),
            "space_commit_url": str(getattr(commit, "commit_url", "") or ""),
            "previous_space_revision": hf_attr(before, "sha"),
            "organization_card": HF_ORG_CARD,
            "organization_card_repo_type": org_type,
            "organization_card_commit_url": str(getattr(card_commit, "commit_url", "") or ""),
            "organization_card_marker_present": True,
        }
        receipt["product"] = {
            "url": "https://a-11-oy.com/code",
            "http_status": product_status,
            "body_sha256": sha256_bytes(product_body),
            "provider_readiness_inferred": False,
        }

    receipt["completed_at"] = utcnow()
    receipt["complete"] = True
    receipt_path.parent.mkdir(parents=True, exist_ok=True)
    receipt_path.write_text(
        json.dumps(receipt, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    return receipt


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--manifest", type=Path, required=True)
    parser.add_argument("--card", type=Path, required=True)
    parser.add_argument(
        "--receipt",
        type=Path,
        default=Path("artifacts/llm-router-flagship-restoration-v2.json"),
    )
    parser.add_argument("--wait-seconds", type=int, default=1200)
    parser.add_argument("--apply", action="store_true")
    args = parser.parse_args()
    validate_contract(args.manifest, args.card)
    if not args.apply:
        print("LLM Router exact-runtime flagship contract v2 is valid")
        return 0
    result = restore(args.manifest, args.card, args.receipt, args.wait_seconds)
    print(json.dumps(result, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
