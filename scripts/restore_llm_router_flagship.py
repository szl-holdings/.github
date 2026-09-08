#!/usr/bin/env python3
"""Restore the SZL LLM Router authority chain from GitHub to Hugging Face.

This controller is intentionally narrow. It may unarchive and relabel the
existing ``szl-holdings/szl-router`` repository, publish the exact ``space/``
folder from one immutable GitHub revision to the existing
``SZLHOLDINGS/llm-router-live`` Space, make that Space public, restart it, and
insert the source-controlled flagship block into the Hugging Face organization
card.

It never creates a second router repository, never copies secrets into an
artifact, never weakens branch protection, and never treats an HTTP 200 or a
RUNNING Space as proof of model quality or provider availability.
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
GITHUB_REPOSITORY = "szl-holdings/szl-router"
HF_SPACE = "SZLHOLDINGS/llm-router-live"
HF_ORG_CARD = "SZLHOLDINGS/README"
MARKER_BEGIN = "<!-- SZL_LLM_ROUTER_FLAGSHIP:BEGIN -->"
MARKER_END = "<!-- SZL_LLM_ROUTER_FLAGSHIP:END -->"
SHA40 = re.compile(r"^[0-9a-f]{40}$")
MAX_ARCHIVE_BYTES = 75 * 1024 * 1024
USER_AGENT = "szl-llm-router-flagship-restorer/1.0"


class RestoreError(RuntimeError):
    """Fail-closed restoration error."""


def utcnow() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def sha256_bytes(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def require_env(name: str) -> str:
    value = os.environ.get(name, "").strip()
    if not value:
        raise RestoreError(f"required environment variable {name} is absent")
    return value


def github_request(
    token: str,
    method: str,
    path: str,
    *,
    payload: Mapping[str, Any] | None = None,
    expected: Iterable[int] = (200,),
    max_bytes: int = 8 * 1024 * 1024,
) -> tuple[int, Any, Mapping[str, str]]:
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
        data=body,
        headers=headers,
        method=method,
    )
    try:
        with urllib.request.urlopen(
            request,
            timeout=45,
            context=ssl.create_default_context(),
        ) as response:
            raw = response.read(max_bytes + 1)
            if len(raw) > max_bytes:
                raise RestoreError(f"GitHub response exceeded {max_bytes} bytes")
            if response.status not in set(expected):
                raise RestoreError(
                    f"GitHub returned unexpected HTTP {response.status} for {method} {path}"
                )
            parsed: Any = None
            if raw:
                try:
                    parsed = json.loads(raw)
                except json.JSONDecodeError:
                    parsed = raw
            return response.status, parsed, dict(response.headers.items())
    except urllib.error.HTTPError as exc:
        # Do not echo a provider body: it can reflect request or credential context.
        raise RestoreError(f"GitHub returned HTTP {exc.code} for {method} {path}") from exc
    except (urllib.error.URLError, TimeoutError, OSError) as exc:
        raise RestoreError(f"GitHub transport failed for {method} {path}") from exc


def download_github_archive(token: str, revision: str, destination: Path) -> None:
    request = urllib.request.Request(
        f"{GITHUB_API}/repos/{GITHUB_REPOSITORY}/zipball/{revision}",
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
            raw = response.read(MAX_ARCHIVE_BYTES + 1)
    except (urllib.error.HTTPError, urllib.error.URLError, TimeoutError, OSError) as exc:
        raise RestoreError("failed to download the exact GitHub source archive") from exc
    if len(raw) > MAX_ARCHIVE_BYTES:
        raise RestoreError("GitHub source archive exceeded the bounded size")
    destination.write_bytes(raw)


def safe_extract_zip(archive: Path, destination: Path) -> Path:
    with zipfile.ZipFile(archive) as bundle:
        roots: set[str] = set()
        for member in bundle.infolist():
            path = Path(member.filename)
            if path.is_absolute() or ".." in path.parts:
                raise RestoreError("source archive contains an unsafe path")
            if path.parts:
                roots.add(path.parts[0])
        if len(roots) != 1:
            raise RestoreError("source archive did not contain one repository root")
        bundle.extractall(destination)
    return destination / next(iter(roots))


def ensure_space_frontmatter(readme: Path, revision: str) -> None:
    existing = readme.read_text(encoding="utf-8") if readme.exists() else ""
    if existing.startswith("---\n"):
        end = existing.find("\n---\n", 4)
    else:
        end = -1
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
    if end >= 0:
        frontmatter = existing[4:end].splitlines()
        seen: set[str] = set()
        output: list[str] = []
        for line in frontmatter:
            key = line.split(":", 1)[0].strip() if ":" in line else ""
            if key in required:
                if key not in seen:
                    output.append(f"{key}: {required[key]}")
                    seen.add(key)
            else:
                output.append(line)
        for key, value in required.items():
            if key not in seen:
                output.append(f"{key}: {value}")
        body = existing[end + 5 :].lstrip("\n")
        rendered = "---\n" + "\n".join(output) + "\n---\n\n" + body
    else:
        rendered = (
            "---\n"
            + "\n".join(f"{key}: {value}" for key, value in required.items())
            + "\n---\n\n"
            + existing
        )
    notice = (
        f"<!-- exact_source: {GITHUB_REPOSITORY}@{revision} -->\n"
        "<!-- classification: FLAGSHIP; runtime truth remains independently observed -->\n"
    )
    if "<!-- exact_source:" in rendered:
        rendered = re.sub(
            r"<!-- exact_source: .*? -->\n(?:<!-- classification: .*? -->\n)?",
            notice,
            rendered,
            count=1,
        )
    else:
        split = rendered.find("\n---\n", 4)
        insertion = split + 5 if split >= 0 else 0
        rendered = rendered[:insertion] + "\n" + notice + rendered[insertion:]
    readme.write_text(rendered, encoding="utf-8", newline="\n")


def insert_card_block(existing: str, block: str) -> str:
    block = block.strip() + "\n"
    if MARKER_BEGIN not in block or MARKER_END not in block:
        raise RestoreError("flagship card source is missing its idempotency markers")
    if MARKER_BEGIN in existing and MARKER_END in existing:
        pattern = re.compile(
            re.escape(MARKER_BEGIN) + r".*?" + re.escape(MARKER_END) + r"\n?",
            re.DOTALL,
        )
        return pattern.sub(block, existing, count=1)
    if existing.startswith("---\n"):
        end = existing.find("\n---\n", 4)
        if end >= 0:
            insertion = end + 5
            return existing[:insertion] + "\n\n" + block + "\n" + existing[insertion:].lstrip("\n")
    return block + "\n" + existing


def hf_attr(value: Any, name: str, default: Any = None) -> Any:
    result = getattr(value, name, default)
    if result is not default:
        return result
    raw = getattr(value, "raw", None)
    if isinstance(raw, Mapping):
        return raw.get(name, default)
    return default


def restore(
    *,
    manifest_path: Path,
    card_path: Path,
    receipt_path: Path,
    wait_seconds: int,
) -> dict[str, Any]:
    github_token = require_env("ROUTER_GH_TOKEN")
    hf_token = require_env("HF_TOKEN")
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    if manifest.get("classification") != "FLAGSHIP":
        raise RestoreError("manifest does not declare the router as a FLAGSHIP")
    if manifest.get("github_source", {}).get("repository") != GITHUB_REPOSITORY:
        raise RestoreError("manifest GitHub source does not match the controller")
    if manifest.get("hugging_face_runtime", {}).get("repository") != HF_SPACE:
        raise RestoreError("manifest Hugging Face Space does not match the controller")

    receipt: dict[str, Any] = {
        "schema": "szl.llm-router-flagship-restoration/v1",
        "started_at": utcnow(),
        "manifest_sha256": sha256_bytes(manifest_path.read_bytes()),
        "card_sha256": sha256_bytes(card_path.read_bytes()),
        "github": {},
        "hugging_face": {},
        "product": {},
        "complete": False,
        "authorization_proof": False,
    }

    # 1. Restore the canonical GitHub source without bypassing branch rules.
    github_request(
        github_token,
        "PATCH",
        f"/repos/{GITHUB_REPOSITORY}",
        payload={
            "archived": False,
            "description": (
                "FLAGSHIP: sovereign-first OpenAI-compatible LLM router with "
                "verifiable routing receipts; source of truth for "
                "SZLHOLDINGS/llm-router-live"
            ),
            "homepage": "https://a-11-oy.com/code",
            "has_issues": True,
        },
    )
    _, repository, _ = github_request(
        github_token,
        "GET",
        f"/repos/{GITHUB_REPOSITORY}",
    )
    if not isinstance(repository, Mapping) or repository.get("archived") is not False:
        raise RestoreError("GitHub did not report the router repository as unarchived")
    github_request(
        github_token,
        "PUT",
        f"/repos/{GITHUB_REPOSITORY}/topics",
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
    default_branch = str(repository.get("default_branch") or "main")
    _, branch, _ = github_request(
        github_token,
        "GET",
        f"/repos/{GITHUB_REPOSITORY}/branches/{urllib.parse.quote(default_branch, safe='')}",
    )
    revision = str((branch.get("commit") or {}).get("sha") if isinstance(branch, Mapping) else "")
    if not SHA40.fullmatch(revision):
        raise RestoreError("GitHub default branch did not expose an exact 40-character revision")
    receipt["github"] = {
        "repository": GITHUB_REPOSITORY,
        "archived": False,
        "default_branch": default_branch,
        "source_revision": revision,
        "description": repository.get("description"),
        "homepage": repository.get("homepage"),
    }

    # 2. Stage the exact source-owned Space context.
    with tempfile.TemporaryDirectory(prefix="szl-router-restore-") as temporary:
        temp = Path(temporary)
        archive = temp / "source.zip"
        extract = temp / "source"
        extract.mkdir()
        download_github_archive(github_token, revision, archive)
        root = safe_extract_zip(archive, extract)
        source_space = root / "space"
        if not source_space.is_dir():
            raise RestoreError("the exact router source does not contain the required space/ folder")
        stage = temp / "space-stage"
        shutil.copytree(source_space, stage)
        ensure_space_frontmatter(stage / "README.md", revision)
        (stage / "source_revision.txt").write_text(revision + "\n", encoding="ascii")
        provenance = {
            "schema": "szl.space-provenance/v1",
            "classification": "FLAGSHIP",
            "github_repository": GITHUB_REPOSITORY,
            "github_revision": revision,
            "hugging_face_repository": HF_SPACE,
            "generated_at": utcnow(),
            "provider_credentials_embedded": False,
            "authority_created": False,
        }
        (stage / "SPACE_PROVENANCE.json").write_text(
            json.dumps(provenance, indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )

        try:
            from huggingface_hub import HfApi, hf_hub_download
            from huggingface_hub.errors import RepositoryNotFoundError
        except ImportError as exc:
            raise RestoreError("huggingface_hub is not installed") from exc

        api = HfApi(token=hf_token)
        try:
            before = api.repo_info(repo_id=HF_SPACE, repo_type="space", token=hf_token)
        except RepositoryNotFoundError as exc:
            raise RestoreError(
                "the existing llm-router-live Space is not visible to the configured HF token; "
                "the controller will not create a second Space"
            ) from exc

        api.update_repo_settings(
            repo_id=HF_SPACE,
            repo_type="space",
            private=False,
            token=hf_token,
        )
        commit = api.upload_folder(
            repo_id=HF_SPACE,
            repo_type="space",
            folder_path=str(stage),
            path_in_repo=".",
            commit_message=f"Restore flagship from {GITHUB_REPOSITORY}@{revision}",
            token=hf_token,
        )
        api.restart_space(repo_id=HF_SPACE, token=hf_token)

        deadline = time.monotonic() + wait_seconds
        stage_name = "UNKNOWN"
        hub_revision = None
        runtime_revision = None
        while time.monotonic() < deadline:
            info = api.repo_info(repo_id=HF_SPACE, repo_type="space", token=hf_token)
            hub_revision = hf_attr(info, "sha")
            runtime = hf_attr(info, "runtime")
            stage_name = str(hf_attr(runtime, "stage", "UNKNOWN") or "UNKNOWN").upper()
            runtime_revision = hf_attr(runtime, "sha")
            if stage_name == "RUNNING" and hub_revision:
                if runtime_revision in (None, hub_revision):
                    break
            if stage_name in {"BUILD_ERROR", "RUNTIME_ERROR", "CONFIG_ERROR", "NO_APP_FILE"}:
                raise RestoreError(f"Hugging Face runtime entered terminal stage {stage_name}")
            time.sleep(15)
        else:
            raise RestoreError(
                f"Hugging Face Space did not reach exact RUNNING state within {wait_seconds} seconds; "
                f"last stage={stage_name}"
            )

        receipt["hugging_face"]["space"] = {
            "repository": HF_SPACE,
            "private": False,
            "stage": stage_name,
            "repository_revision": hub_revision,
            "runtime_revision": runtime_revision,
            "source_revision": revision,
            "commit_url": str(getattr(commit, "commit_url", "") or ""),
            "previous_revision": hf_attr(before, "sha"),
        }

        # 3. Insert the source-controlled flagship card into the HF organization card.
        org_type = None
        current_readme = ""
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
                    current_readme = Path(local).read_text(encoding="utf-8")
                except Exception:
                    current_readme = ""
                break
            except Exception:
                continue
        if org_type is None:
            raise RestoreError("the SZLHOLDINGS organization-card repository was not found")
        card_block = card_path.read_text(encoding="utf-8")
        rendered = insert_card_block(current_readme, card_block)
        api.upload_file(
            repo_id=HF_ORG_CARD,
            repo_type=org_type,
            path_or_fileobj=rendered.encode("utf-8"),
            path_in_repo="README.md",
            commit_message=f"Showcase SZL LLM Router flagship at {revision[:12]}",
            token=hf_token,
        )
        receipt["hugging_face"]["organization_card"] = {
            "repository": HF_ORG_CARD,
            "repo_type": org_type,
            "flagship_marker_present": True,
            "rendered_sha256": sha256_bytes(rendered.encode("utf-8")),
        }

    # 4. Verify the integrated product interface without equating it with model readiness.
    product_request = urllib.request.Request(
        "https://a-11-oy.com/code",
        headers={"User-Agent": USER_AGENT, "Accept": "text/html"},
    )
    try:
        with urllib.request.urlopen(
            product_request,
            timeout=30,
            context=ssl.create_default_context(),
        ) as response:
            product_status = int(response.status)
            product_body = response.read(2_000_001)
    except (urllib.error.HTTPError, urllib.error.URLError, TimeoutError, OSError) as exc:
        raise RestoreError("A11oy router product surface could not be verified") from exc
    if product_status != 200 or len(product_body) > 2_000_000:
        raise RestoreError("A11oy router product surface did not return a bounded HTTP 200 response")
    receipt["product"] = {
        "url": "https://a-11-oy.com/code",
        "http_status": product_status,
        "body_sha256": sha256_bytes(product_body),
        "model_provider_readiness_inferred": False,
    }

    receipt["completed_at"] = utcnow()
    receipt["complete"] = True
    receipt_path.parent.mkdir(parents=True, exist_ok=True)
    receipt_path.write_text(
        json.dumps(receipt, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    return receipt


def validate(manifest_path: Path, card_path: Path) -> None:
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    assert manifest["classification"] == "FLAGSHIP"
    assert manifest["github_source"]["repository"] == GITHUB_REPOSITORY
    assert manifest["github_source"]["must_be_archived"] is False
    assert manifest["hugging_face_runtime"]["repository"] == HF_SPACE
    assert manifest["hugging_face_runtime"]["showcase_on_org_card"] is True
    assert manifest["runtime_contract"]["provider_keys_committed"] is False
    card = card_path.read_text(encoding="utf-8")
    assert MARKER_BEGIN in card and MARKER_END in card
    assert "GitHub source" in card
    assert "Hugging Face runtime" in card
    assert "Conjecture 1" in card


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--manifest", type=Path, required=True)
    parser.add_argument("--card", type=Path, required=True)
    parser.add_argument(
        "--receipt",
        type=Path,
        default=Path("artifacts/llm-router-flagship-restoration.json"),
    )
    parser.add_argument("--wait-seconds", type=int, default=1200)
    parser.add_argument("--apply", action="store_true")
    args = parser.parse_args()
    validate(args.manifest, args.card)
    if not args.apply:
        print("LLM router flagship recovery contract is valid")
        return 0
    receipt = restore(
        manifest_path=args.manifest,
        card_path=args.card,
        receipt_path=args.receipt,
        wait_seconds=args.wait_seconds,
    )
    print(json.dumps(receipt, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
