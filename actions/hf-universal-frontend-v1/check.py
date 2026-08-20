#!/usr/bin/env python3
from __future__ import annotations

import argparse
import hashlib
from html.parser import HTMLParser
import json
import posixpath
import re
from pathlib import Path
from typing import Any
from urllib.parse import unquote, urlsplit

SCHEMA = "szl.hf-universal-frontend/v1"
ALLOWED_FRAMEWORKS = {"static", "gradio", "streamlit", "react"}
FRAMEWORK_SDKS = {
    "static": frozenset({"static"}),
    "gradio": frozenset({"gradio"}),
    "streamlit": frozenset({"streamlit", "docker"}),
    "react": frozenset({"static", "docker"}),
}
PYTHON_MARKER = "# SZL_HF_UNIVERSAL_FRONTEND_V1"
REACT_MARKER = "// SZL_HF_UNIVERSAL_FRONTEND_V1"
REQUIRED_CSS_TOKENS = (
    "--szl-touch-target: 44px",
    "overflow-wrap: anywhere",
    "overflow-x: clip",
    "@media (max-width: 560px)",
    "@media (prefers-reduced-motion: reduce)",
)
SHA256 = re.compile(r"^[0-9a-f]{64}$")
MAX_OUTPUT_VALUE_BYTES = 4096


class ContractError(RuntimeError):
    pass


class _StaticDocumentParser(HTMLParser):
    _INERT_CONTAINERS = frozenset({"noscript", "template"})

    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.has_viewport = False
        self.has_base = False
        self.stylesheet_links: list[dict[str, str]] = []
        self._inert_stack: list[str] = []

    @property
    def has_unclosed_inert_container(self) -> bool:
        return bool(self._inert_stack)

    def handle_starttag(
        self,
        tag: str,
        attrs: list[tuple[str, str | None]],
    ) -> None:
        normalized_tag = tag.casefold()
        if normalized_tag in self._INERT_CONTAINERS:
            self._inert_stack.append(normalized_tag)
            return
        if self._inert_stack:
            return
        self._record(tag, attrs)

    def handle_startendtag(
        self,
        tag: str,
        attrs: list[tuple[str, str | None]],
    ) -> None:
        normalized_tag = tag.casefold()
        if normalized_tag in self._INERT_CONTAINERS:
            raise ContractError(
                f"Static application contains self-closing <{normalized_tag}>"
            )
        if self._inert_stack:
            return
        self._record(tag, attrs)

    def handle_endtag(self, tag: str) -> None:
        normalized_tag = tag.casefold()
        if not self._inert_stack or normalized_tag not in self._INERT_CONTAINERS:
            return
        expected = self._inert_stack[-1]
        if normalized_tag != expected:
            raise ContractError(
                "Static application contains mismatched inert containers: "
                f"expected </{expected}>, received </{normalized_tag}>"
            )
        self._inert_stack.pop()

    def _record(
        self,
        tag: str,
        attrs: list[tuple[str, str | None]],
    ) -> None:
        values: dict[str, str] = {}
        duplicates: set[str] = set()
        for name, value in attrs:
            key = str(name).casefold()
            if key in values:
                duplicates.add(key)
                continue
            values[key] = "" if value is None else str(value)
        normalized_tag = tag.casefold()
        if normalized_tag == "base":
            self.has_base = True
            return
        if normalized_tag == "meta" and values.get("name", "").casefold() == "viewport":
            self.has_viewport = True
        if normalized_tag != "link":
            return
        security_attributes = {
            "rel",
            "href",
            "data-szl-universal-frontend",
            "disabled",
            "media",
            "type",
        }
        ambiguous = sorted(duplicates & security_attributes)
        if ambiguous:
            raise ContractError(
                "Static stylesheet link contains duplicate controlled attributes: "
                + ", ".join(ambiguous)
            )
        rel_tokens = {
            token.casefold()
            for token in values.get("rel", "").split()
            if token.strip()
        }
        if "stylesheet" not in rel_tokens or "alternate" in rel_tokens:
            return
        if "disabled" in values:
            return
        media = values.get("media", "").strip().casefold()
        if media not in {"", "all"}:
            return
        content_type = values.get("type", "").strip().casefold()
        if content_type not in {"", "text/css"}:
            return
        self.stylesheet_links.append(values)


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _reject_line_breaks(value: str, label: str) -> None:
    if "\r" in value or "\n" in value:
        raise ContractError(f"{label} may not contain CR or LF characters")


def safe_path(root: Path, value: Any, label: str) -> Path:
    if isinstance(value, Path):
        value = str(value)
    if not isinstance(value, str) or not value.strip():
        raise ContractError(f"{label} is absent or not a string")
    _reject_line_breaks(value, label)
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


def validate_front_matter(values: dict[str, str], manifest: dict[str, Any]) -> str:
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
    return sdk.strip().casefold()


def validate_sdk_binding(card_sdk: str, manifest: dict[str, Any], framework: str) -> str:
    manifest_sdk = manifest.get("sdk")
    if not isinstance(manifest_sdk, str) or not manifest_sdk.strip():
        raise ContractError("manifest sdk is absent or not a string")
    normalized = manifest_sdk.strip().casefold()
    if card_sdk != normalized:
        raise ContractError(
            f"README sdk {card_sdk!r} diverges from manifest sdk {normalized!r}"
        )
    compatible = FRAMEWORK_SDKS[framework]
    if normalized not in compatible:
        allowed = ", ".join(sorted(compatible))
        raise ContractError(
            f"sdk {normalized!r} is not compatible with framework {framework!r}; expected one of: {allowed}"
        )
    return normalized


def _strip_css_inert_text(css_text: str) -> str:
    """Blank comments and strings without joining tokens across them."""
    output: list[str] = []
    index = 0

    def blank(character: str) -> str:
        return character if character in {"\r", "\n"} else " "

    while index < len(css_text):
        if css_text.startswith("/*", index):
            output.extend((" ", " "))
            index += 2
            while index < len(css_text):
                if css_text.startswith("*/", index):
                    output.extend((" ", " "))
                    index += 2
                    break
                output.append(blank(css_text[index]))
                index += 1
            continue

        character = css_text[index]
        if character not in {"'", '"'}:
            output.append(character)
            index += 1
            continue

        quote = character
        output.append(" ")
        index += 1
        while index < len(css_text):
            character = css_text[index]
            output.append(blank(character))
            index += 1
            if character == "\\" and index < len(css_text):
                output.append(blank(css_text[index]))
                index += 1
                continue
            if character == quote:
                break

    return "".join(output)


def validate_css(css_text: str) -> None:
    active_css = _strip_css_inert_text(css_text)
    missing = [token for token in REQUIRED_CSS_TOKENS if token not in active_css]
    if missing:
        raise ContractError("universal CSS is missing required active tokens: " + ", ".join(missing))


def _resolved_static_href(app_file: str, href: str) -> str:
    _reject_line_breaks(href, "static stylesheet href")
    parsed = urlsplit(href)
    if parsed.scheme or parsed.netloc:
        raise ContractError("static universal stylesheet href must be repository-local")
    decoded = unquote(parsed.path)
    _reject_line_breaks(decoded, "decoded static stylesheet href")
    if not decoded or decoded.startswith("/") or "\\" in decoded:
        raise ContractError("static universal stylesheet href must be a relative POSIX path")
    resolved = posixpath.normpath(posixpath.join(posixpath.dirname(app_file), decoded))
    if resolved == ".." or resolved.startswith("../"):
        raise ContractError("static universal stylesheet href escapes the application directory")
    return resolved


def validate_framework_binding(
    framework: str,
    app_text: str,
    *,
    app_file: str,
    css_file: str,
) -> None:
    if framework in {"gradio", "streamlit"} and PYTHON_MARKER not in app_text:
        raise ContractError("Python frontend binding marker is absent")
    if framework == "gradio" and "_SZL_UNIVERSAL_CSS" not in app_text:
        raise ContractError("Gradio universal CSS binding is absent")
    if framework == "streamlit" and "unsafe_allow_html=True" not in app_text:
        raise ContractError("Streamlit universal CSS binding is absent")
    if framework == "static":
        parser = _StaticDocumentParser()
        parser.feed(app_text)
        parser.close()
        if parser.has_unclosed_inert_container:
            raise ContractError("Static application contains an unclosed inert container")
        if not parser.has_viewport:
            raise ContractError("Static viewport metadata is absent")
        if parser.has_base:
            raise ContractError(
                "Static application may not override repository-local URL resolution with <base>"
            )
        expected_css = posixpath.normpath(css_file)
        for link in parser.stylesheet_links:
            if link.get("data-szl-universal-frontend") != "v1":
                continue
            href = link.get("href", "")
            if _resolved_static_href(app_file, href) == expected_css:
                break
        else:
            raise ContractError(
                "Static universal CSS requires a stylesheet <link> whose marker and href bind the declared css_file"
            )
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
    card_sdk = validate_front_matter(front, manifest)
    sdk = validate_sdk_binding(card_sdk, manifest, framework)
    validate_css(css.read_text(encoding="utf-8"))
    # A static Space serves app_file directly. entry_file is relevant to
    # source-based adapters, but it must not redirect validation to a decoy
    # document while the served HTML omits the declared stylesheet.
    binding_path = app if framework == "static" else (entry or app)
    binding_relative = (
        str(manifest["app_file"])
        if framework == "static"
        else str(manifest.get("entry_file") or manifest["app_file"])
    )
    validate_framework_binding(
        framework,
        binding_path.read_text(encoding="utf-8"),
        app_file=binding_relative,
        css_file=str(manifest["css_file"]),
    )

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
        "sdk": sdk,
        "app_file": manifest.get("app_file"),
        "css_file": manifest.get("css_file"),
        "entry_file": manifest.get("entry_file"),
        "manifest_path": str(manifest_path),
        "manifest_sha256": sha256(manifest_full),
        "verified_files": hashes,
        "remote_mutation": False,
    }


def _github_output_value(name: str, value: Any) -> str:
    text = "" if value is None else str(value)
    _reject_line_breaks(text, f"GitHub output {name}")
    if len(text.encode("utf-8")) > MAX_OUTPUT_VALUE_BYTES:
        raise ContractError(
            f"GitHub output {name} exceeds {MAX_OUTPUT_VALUE_BYTES} bytes"
        )
    return text


def write_github_output(path: Path, result: dict[str, Any]) -> None:
    lines = {
        "status": result["status"],
        "framework": result["framework"],
        "app_file": result["app_file"],
        "css_file": result["css_file"],
        "manifest_sha256": result["manifest_sha256"],
    }
    # Authenticate every value before opening the environment file. A rejected
    # value must not leave a partial set of outputs behind.
    records = [
        f"{key}={_github_output_value(key, value)}\n"
        for key, value in lines.items()
    ]
    with path.open("a", encoding="utf-8") as handle:
        handle.writelines(records)


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
        if args.github_output:
            write_github_output(args.github_output, result)
    except (ContractError, OSError, ValueError) as error:
        print(json.dumps({"status": "FAIL", "error": str(error)}, indent=2, sort_keys=True))
        return 1
    print(json.dumps(result, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
