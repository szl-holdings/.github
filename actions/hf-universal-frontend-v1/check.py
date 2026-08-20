#!/usr/bin/env python3
from __future__ import annotations

import argparse
import hashlib
import json
import re
from pathlib import Path
from typing import Any

SCHEMA = "szl.hf-universal-frontend/v1"
ALLOWED_FRAMEWORKS = {"static", "gradio", "streamlit", "react"}
PYTHON_MARKER = "# SZL_HF_UNIVERSAL_FRONTEND_V1"
HTML_MARKER = 'data-szl-universal-frontend="v1"'
REACT_MARKER = "// SZL_HF_UNIVERSAL_FRONTEND_V1"
REQUIRED_CSS_TOKENS = (
    "--szl-touch-target: 44px",
    "overflow-wrap: anywhere",
    "overflow-x: clip",
    "@media (max-width: 560px)",
    "@media (prefers-reduced-motion: reduce)",
)
SHA256 = re.compile(r"^[0-9a-f]{64}$")


class ContractError(RuntimeError):
    pass


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def safe_path(root: Path, value: Any, label: str) -> Path:
    if isinstance(value, Path):
        value = str(value)
    if not isinstance(value, str) or not value.strip():
        raise ContractError(f"{label} is absent or not a string")
    relative = Path(value)
    if relative.is_absolute() or ".." in relative.parts:
        raise ContractError(f"{label} must be a safe repository-relative path: {value!r}")
    resolved_root = root.resolve()
    unresolved = resolved_root / relative
    cursor = resolved_root
    for part in relative.parts:
        cursor /= part
        if cursor.is_symlink():
            raise ContractError(f"{label} may not contain a symlink: {value!r}")
    path = unresolved.resolve()
    try:
        path.relative_to(resolved_root)
    except ValueError as error:
        raise ContractError(f"{label} escapes the repository root: {value!r}") from error
    if not path.is_file():
        raise ContractError(f"{label} does not exist: {value!r}")
    return path


def parse_front_matter(text: str) -> dict[str, str]:
    if not text.startswith("---\n"):
        raise ContractError("README.md must start with Hugging Face YAML front matter")
    end = text.find("\n---\n", 4)
    if end < 0:
        raise ContractError("README.md Hugging Face front matter is not terminated")
    values: dict[str, str] = {}
    duplicates: set[str] = set()
    for line in text[4:end].splitlines():
        match = re.match(r"^([A-Za-z0-9_-]+)\s*:\s*(.*?)\s*$", line)
        if not match:
            continue
        key = match.group(1)
        value = match.group(2).strip()
        if len(value) >= 2 and value[0] == value[-1] and value[0] in {"'", '"'}:
            value = value[1:-1]
        if key in values:
            duplicates.add(key)
        values[key] = value.strip()
    if duplicates:
        raise ContractError("README.md contains duplicate front-matter keys: " + ", ".join(sorted(duplicates)))
    return values


def validate_front_matter(values: dict[str, str], manifest: dict[str, Any]) -> None:
    short = values.get("short_description") or values.get("shortDescription")
    if not short:
        raise ContractError("short_description is absent")
    if len(short) > 60:
        raise ContractError(f"short_description exceeds 60 characters: {len(short)}")
    if values.get("fullWidth", "").lower() != "true":
        raise ContractError("fullWidth must be true")
    if values.get("header") != "mini":
        raise ContractError("header must be mini")
    sdk = values.get("sdk")
    if not sdk:
        raise ContractError("sdk is absent from README.md front matter")
    app_file = values.get("app_file") or values.get("appFile")
    if app_file and app_file != manifest.get("app_file"):
        raise ContractError(
            f"README app_file {app_file!r} diverges from manifest app_file {manifest.get('app_file')!r}"
        )


def validate_css(css_text: str) -> None:
    missing = [token for token in REQUIRED_CSS_TOKENS if token not in css_text]
    if missing:
        raise ContractError("universal CSS is missing required tokens: " + ", ".join(missing))


def validate_framework_binding(framework: str, app_text: str) -> None:
    if framework in {"gradio", "streamlit"} and PYTHON_MARKER not in app_text:
        raise ContractError("Python frontend binding marker is absent")
    if framework == "gradio" and "_SZL_UNIVERSAL_CSS" not in app_text:
        raise ContractError("Gradio universal CSS binding is absent")
    if framework == "streamlit" and "unsafe_allow_html=True" not in app_text:
        raise ContractError("Streamlit universal CSS binding is absent")
    if framework == "static":
        if HTML_MARKER not in app_text:
            raise ContractError("Static universal CSS link marker is absent")
        if not re.search(r"<meta\s+[^>]*name=[\"']viewport[\"']", app_text, re.IGNORECASE):
            raise ContractError("Static viewport metadata is absent")
    if framework == "react" and REACT_MARKER not in app_text:
        raise ContractError("React universal CSS import marker is absent")


def validate_hashes(
    root: Path, hashes: Any, required_paths: set[str]
) -> dict[str, str]:
    if not isinstance(hashes, dict) or not hashes:
        raise ContractError("file_sha256 is absent or empty")
    missing = sorted(required_paths - set(hashes))
    if missing:
        raise ContractError(
            "file_sha256 is missing managed paths: " + ", ".join(missing)
        )
    verified: dict[str, str] = {}
    for relative, expected in sorted(hashes.items()):
        if not isinstance(expected, str) or not SHA256.fullmatch(expected):
            raise ContractError(f"invalid SHA-256 digest for {relative!r}")
        path = safe_path(root, relative, f"file_sha256[{relative!r}]")
        observed = sha256(path)
        if observed != expected:
            raise ContractError(
                f"file hash mismatch for {relative}: expected {expected}, observed {observed}"
            )
        verified[str(relative)] = observed
    return verified


def validate(root: Path, manifest_path: Path) -> dict[str, Any]:
    root = root.resolve()
    if not root.is_dir():
        raise ContractError(f"repository root does not exist: {root}")
    manifest_full = safe_path(root, manifest_path, "manifest")
    try:
        manifest = json.loads(manifest_full.read_text(encoding="utf-8"))
    except json.JSONDecodeError as error:
        raise ContractError(f"manifest is not valid JSON: {error}") from error
    if not isinstance(manifest, dict):
        raise ContractError("manifest root must be a JSON object")
    if manifest.get("schema") != SCHEMA:
        raise ContractError(f"unexpected manifest schema: {manifest.get('schema')!r}")
    if manifest.get("remote_mutation") is not False:
        raise ContractError("manifest remote_mutation must be false")
    framework = manifest.get("framework")
    if framework not in ALLOWED_FRAMEWORKS:
        raise ContractError(f"unsupported framework: {framework!r}")

    # Resolve every manifest-controlled path before comparing descriptive
    # metadata. This keeps traversal and containment failures authoritative.
    readme = safe_path(root, "README.md", "README.md")
    app = safe_path(root, manifest.get("app_file"), "app_file")
    css = safe_path(root, manifest.get("css_file"), "css_file")
    entry = None
    if manifest.get("entry_file"):
        entry = safe_path(root, manifest.get("entry_file"), "entry_file")

    # Authenticate managed bytes before interpreting their contents. A changed
    # file must report hash drift rather than an incidental downstream parse or
    # framework-binding error.
    required_hashes = {
        "README.md",
        str(manifest["app_file"]),
        str(manifest["css_file"]),
    }
    if manifest.get("entry_file"):
        required_hashes.add(str(manifest["entry_file"]))
    hashes = validate_hashes(
        root, manifest.get("file_sha256"), required_hashes
    )

    front = parse_front_matter(readme.read_text(encoding="utf-8"))
    validate_front_matter(front, manifest)
    validate_css(css.read_text(encoding="utf-8"))
    binding_path = entry or app
    validate_framework_binding(framework, binding_path.read_text(encoding="utf-8"))

    contract = manifest.get("contract")
    if not isinstance(contract, dict):
        raise ContractError("manifest contract is absent")
    if contract.get("minimum_touch_target_px") != 44:
        raise ContractError("minimum_touch_target_px must be 44")
    if contract.get("horizontal_overflow_allowed") is not False:
        raise ContractError("horizontal_overflow_allowed must be false")
    if contract.get("reduced_motion_required") is not True:
        raise ContractError("reduced_motion_required must be true")
    if contract.get("technical_identifier_wrapping_required") is not True:
        raise ContractError("technical_identifier_wrapping_required must be true")
    viewports = contract.get("viewport_classes")
    if viewports != [360, 390, 768, 1024, 1440]:
        raise ContractError(f"unexpected viewport_classes: {viewports!r}")

    return {
        "schema": "szl.hf-universal-frontend-contract-result/v1",
        "status": "PASS",
        "framework": framework,
        "sdk": manifest.get("sdk"),
        "app_file": manifest.get("app_file"),
        "css_file": manifest.get("css_file"),
        "entry_file": manifest.get("entry_file"),
        "manifest_path": str(manifest_path),
        "manifest_sha256": sha256(manifest_full),
        "verified_files": hashes,
        "remote_mutation": False,
    }


def write_github_output(path: Path, result: dict[str, Any]) -> None:
    lines = {
        "status": result["status"],
        "framework": result["framework"],
        "app_file": result["app_file"],
        "css_file": result["css_file"],
        "manifest_sha256": result["manifest_sha256"],
    }
    with path.open("a", encoding="utf-8") as handle:
        for key, value in lines.items():
            handle.write(f"{key}={value}\n")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", type=Path, default=Path.cwd())
    parser.add_argument(
        "--manifest",
        type=Path,
        default=Path("docs/hf-universal-frontend-v1.json"),
    )
    parser.add_argument("--github-output", type=Path)
    args = parser.parse_args()
    try:
        result = validate(args.root, args.manifest)
    except (ContractError, OSError, ValueError) as error:
        print(json.dumps({"status": "FAIL", "error": str(error)}, indent=2, sort_keys=True))
        return 1
    if args.github_output:
        write_github_output(args.github_output, result)
    print(json.dumps(result, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
