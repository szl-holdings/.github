#!/usr/bin/env python3
"""
SZL Production Auditor v5

Fail-closed, evidence-emitting audit for local repositories, public web
surfaces, GitHub metadata/rulesets, and Hugging Face public or authorized
inventory.

External behavior is read-only. The auditor never pushes, merges, edits
rulesets, publishes Hub artifacts, starts Jobs, deploys, or reads back secret
values. Optional --execute-tools commands can write only local build/test
artifacts and caches.

Exit codes:
  0 all required gates PASS
  1 PASS with non-blocking warnings
  2 blocking failure or required UNKNOWN/PARTIAL
  3 invalid profile or auditor failure
"""
from __future__ import annotations

import argparse
import csv
import hashlib
import json
import os
import re
import shlex
import shutil
import socket
import ssl
import subprocess
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
import xml.etree.ElementTree as ET
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timezone
from html.parser import HTMLParser
from pathlib import Path
from typing import Any, Iterable, Mapping, Sequence

VERSION = "5.0.0"
USER_AGENT = f"szl-production-auditor/{VERSION}"
SKIP_DIRS = {
    ".git", "node_modules", ".venv", "venv", "dist", "build", ".next",
    ".turbo", ".cache", "__pycache__", ".pytest_cache", "coverage", "target",
}
TEXT_EXTENSIONS = {
    ".py", ".pyi", ".js", ".mjs", ".cjs", ".ts", ".tsx", ".jsx", ".json",
    ".yaml", ".yml", ".toml", ".ini", ".cfg", ".md", ".html", ".css",
    ".scss", ".sh", ".bash", ".sql", ".graphql", ".proto", ".txt", ".xml",
}
UNSAFE_SERIALIZATION_EXTENSIONS = {".pkl", ".pickle", ".joblib", ".dill"}
WEIGHT_EXTENSIONS = {".safetensors", ".gguf", ".bin", ".pt", ".pth", ".onnx"}
SHA40 = re.compile(r"^[0-9a-f]{40}$", re.I)
ACTION_REF = re.compile(r"^\s*(?:-\s*)?uses:\s*([^@\s]+)@([^\s#]+)", re.M)
SECRET_REGEXES = [
    ("github_token", re.compile(r"gh[pousr]_[A-Za-z0-9]{20,}")),
    ("hf_token", re.compile(r"hf_[A-Za-z0-9]{20,}")),
    ("aws_access_key", re.compile(r"AKIA[0-9A-Z]{16}")),
    ("private_key", re.compile(r"-----BEGIN (?:RSA |EC |OPENSSH )?PRIVATE KEY-----")),
    ("generic_bearer", re.compile(r"Bearer\s+[A-Za-z0-9_.-]{24,}", re.I)),
]
CODE_PATTERNS = [
    ("G13", "P0", "unsafe_pickle_load", re.compile(r"\b(?:pickle|dill)\.loads?\s*\("),
     "Executable serialization load detected."),
    ("G15", "P0", "unsafe_joblib_load", re.compile(r"\bjoblib\.load\s*\("),
     "joblib.load can execute attacker-controlled code."),
    ("G15", "P0", "mutable_remote_code", re.compile(
        r"trust_remote_code\s*=\s*True[\s\S]{0,500}?revision\s*=\s*['\"](?:main|master)['\"]", re.I),
     "Remote executable code is trusted from a mutable branch."),
    ("G08", "P0", "wildcard_cors_credentials", re.compile(
        r"allow_origins\s*=\s*\[\s*['\"]\*['\"]\s*\][\s\S]{0,300}?allow_credentials\s*=\s*True", re.I),
     "Wildcard CORS is combined with credentials."),
    ("G13", "P1", "shell_true", re.compile(
        r"subprocess\.(?:run|Popen|call|check_call|check_output)\([^)]*shell\s*=\s*True", re.S),
     "shell=True requires narrowly justified non-user-controlled input."),
    ("G13", "P1", "dynamic_code_execution", re.compile(r"(?<![\w.])(?:eval|exec)\s*\("),
     "Dynamic code execution requires explicit security review."),
    ("G13", "P1", "debug_enabled", re.compile(r"\bdebug\s*=\s*True\b"),
     "Debug mode appears enabled."),
    ("G08", "P1", "raw_html_injection", re.compile(r"\bdangerouslySetInnerHTML\b|\binnerHTML\s*=", re.I),
     "Raw HTML injection path requires sanitization proof."),
    ("G02", "P2", "todo_fixme_hack", re.compile(r"\b(?:TODO|FIXME|HACK|XXX)\b"),
     "Unresolved engineering marker."),
]


def now() -> str:
    return datetime.now(timezone.utc).isoformat()


def canonical_json(value: Any) -> bytes:
    return (json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False) + "\n").encode()


def file_hash(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def redact(text: str) -> str:
    for _, rx in SECRET_REGEXES:
        text = rx.sub("[REDACTED]", text)
    return text


class Report:
    def __init__(self, profile: dict[str, Any]) -> None:
        self.profile = profile
        self.findings: list[dict[str, Any]] = []
        self.evidence: list[dict[str, Any]] = []

    def finding(
        self, gate: str, severity: str, status: str, target: str, title: str,
        detail: str, remediation: str, *, blocking: bool | None = None,
        evidence: dict[str, Any] | None = None,
    ) -> None:
        if blocking is None:
            blocking = severity in {"P0", "P1"} and status in {"FAIL", "UNKNOWN", "UNAVAILABLE"}
        self.findings.append({
            "finding_id": f"PRD-{len(self.findings)+1:04d}",
            "gate_id": gate, "severity": severity, "status": status,
            "blocking": blocking, "target": target, "title": title,
            "detail": redact(detail), "remediation": remediation,
            "evidence": evidence or {},
        })

    def proof(self, gate: str, control: str, target: str, status: str, **data: Any) -> None:
        self.evidence.append({
            "gate_id": gate, "control": control, "target": target,
            "status": status, "data": data,
        })

    def gate_results(self) -> list[dict[str, Any]]:
        results = []
        for gate in self.profile["gates"]:
            gid = gate["id"]
            findings = [x for x in self.findings if x["gate_id"] == gid]
            evidence = [x for x in self.evidence if x["gate_id"] == gid]
            if any(x["blocking"] and x["status"] == "FAIL" for x in findings):
                status = "FAIL"
            elif any(x["blocking"] and x["status"] in {"UNKNOWN", "UNAVAILABLE"} for x in findings):
                status = "UNKNOWN"
            elif not evidence:
                status = "UNKNOWN"
            elif any(x["status"] in {"UNKNOWN", "UNAVAILABLE"} for x in evidence):
                status = "PARTIAL"
            elif any(x["status"] == "WARN" for x in findings):
                status = "WARN"
            else:
                controls_seen = {x["control"] for x in evidence if x["status"] == "PASS"}
                status = "PASS" if len(controls_seen) >= len(gate.get("controls", [])) else "PARTIAL"
            results.append({
                "id": gid, "name": gate["name"], "domain": gate["domain"],
                "priority": gate["priority"], "block_release": gate["block_release"],
                "status": status, "finding_count": len(findings),
                "evidence_count": len(evidence),
            })
        return results


class PageParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.lang: str | None = None
        self.in_title = False
        self.title_parts: list[str] = []
        self.meta: dict[str, str] = {}
        self.canonical: str | None = None
        self.links: list[str] = []
        self.h1_count = 0
        self.heading_levels: list[int] = []
        self.image_count = 0
        self.images_missing_alt = 0
        self.button_stack: list[dict[str, Any]] = []
        self.unlabelled_buttons = 0
        self.external_scripts: list[str] = []

    @property
    def title(self) -> str:
        return " ".join("".join(self.title_parts).split())

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        tag = tag.lower()
        data = {k.lower(): (v or "") for k, v in attrs}
        if tag == "html":
            self.lang = data.get("lang") or None
        elif tag == "title":
            self.in_title = True
        elif tag == "meta":
            key = (data.get("name") or data.get("property") or "").lower()
            if key:
                self.meta[key] = data.get("content", "")
        elif tag == "link" and "canonical" in data.get("rel", "").lower().split():
            self.canonical = data.get("href") or None
        elif tag == "a" and data.get("href"):
            self.links.append(data["href"])
        elif tag == "img":
            self.image_count += 1
            if "alt" not in data:
                self.images_missing_alt += 1
        elif tag == "h1":
            self.h1_count += 1
            self.heading_levels.append(1)
        elif re.fullmatch(r"h[2-6]", tag):
            self.heading_levels.append(int(tag[1]))
        elif tag == "button":
            self.button_stack.append({
                "named": bool(data.get("aria-label") or data.get("aria-labelledby") or data.get("title")),
                "text": [],
            })
        elif tag == "script" and data.get("src"):
            self.external_scripts.append(data["src"])

    def handle_endtag(self, tag: str) -> None:
        if tag.lower() == "title":
            self.in_title = False
        elif tag.lower() == "button" and self.button_stack:
            button = self.button_stack.pop()
            visible = " ".join("".join(button["text"]).split())
            if not button["named"] and not visible:
                self.unlabelled_buttons += 1

    def handle_data(self, data: str) -> None:
        if self.in_title:
            self.title_parts.append(data)
        if self.button_stack:
            self.button_stack[-1]["text"].append(data)


class HTTP:
    def __init__(self, timeout: float = 12, max_bytes: int = 2_000_000) -> None:
        self.timeout = timeout
        self.max_bytes = max_bytes
        self.context = ssl.create_default_context()

    def request(
        self, url: str, method: str = "GET", token: str | None = None,
        headers: Mapping[str, str] | None = None,
    ) -> tuple[int, dict[str, str], bytes, str]:
        request_headers = {"User-Agent": USER_AGENT, "Accept": "*/*"}
        if token:
            request_headers["Authorization"] = f"Bearer {token}"
        if headers:
            request_headers.update(headers)
        req = urllib.request.Request(url, method=method, headers=request_headers)
        try:
            with urllib.request.urlopen(req, timeout=self.timeout, context=self.context) as resp:
                body = resp.read(self.max_bytes + 1)
                if len(body) > self.max_bytes:
                    raise ValueError(f"response exceeds {self.max_bytes} bytes")
                safe = {k.lower(): redact(v) for k, v in resp.headers.items()}
                return int(resp.status), safe, body, resp.geturl()
        except urllib.error.HTTPError as exc:
            body = exc.read(self.max_bytes + 1)[: self.max_bytes]
            safe = {k.lower(): redact(v) for k, v in exc.headers.items()}
            return int(exc.code), safe, body, exc.geturl()

    def json(self, url: str, token: str | None = None) -> Any:
        status, _, body, _ = self.request(url, token=token, headers={"Accept": "application/json"})
        if status >= 400:
            raise ValueError(f"HTTP {status} for {url}")
        return json.loads(body.decode("utf-8"))


def validate_profile(profile: dict[str, Any]) -> list[str]:
    errors = []
    required = {"schema", "name", "repositories", "web_targets", "gates", "release_rings"}
    if missing := sorted(required - profile.keys()):
        errors.append(f"missing keys: {missing}")
    gate_ids = [x.get("id") for x in profile.get("gates", [])]
    if len(gate_ids) != len(set(gate_ids)):
        errors.append("duplicate gate IDs")
    repo_ids = [x.get("repository") for x in profile.get("repositories", [])]
    if len(repo_ids) != len(set(repo_ids)):
        errors.append("duplicate repository IDs")
    for target in profile.get("web_targets", []):
        if not str(target.get("base_url", "")).startswith("https://"):
            errors.append(f"non-HTTPS target: {target.get('base_url')}")
    return errors


def tls_days(host: str, timeout: float = 8) -> int:
    context = ssl.create_default_context()
    with socket.create_connection((host, 443), timeout=timeout) as sock:
        with context.wrap_socket(sock, server_hostname=host) as wrapped:
            expiry = wrapped.getpeercert().get("notAfter")
    if not expiry:
        raise ValueError("certificate lacks notAfter")
    return int((ssl.cert_time_to_seconds(expiry) - time.time()) // 86400)


def heading_skip(levels: Sequence[int]) -> bool:
    return any(b > a + 1 for a, b in zip(levels, levels[1:]))


def audit_web(target: dict[str, Any], http: HTTP, report: Report, max_pages: int) -> None:
    base = target["base_url"].rstrip("/")
    target_id = target["id"]
    origin = urllib.parse.urlparse(base)
    try:
        days = tls_days(origin.hostname or "")
        report.proof("G13", "TLS certificate inspected", target_id, "PASS", days_until_expiry=days)
        if days < 14:
            report.finding("G13", "P0", "FAIL", target_id, "TLS certificate near expiry",
                           f"{days} days remain", "Renew and verify renewal automation.")
        elif days < 30:
            report.finding("G13", "P1", "WARN", target_id, "TLS renewal window",
                           f"{days} days remain", "Confirm renewal automation and alerting.", blocking=False)
    except Exception as exc:
        report.finding("G13", "P0", "UNKNOWN", target_id, "TLS inspection unavailable",
                       str(exc), "Restore DNS/network and inspect TLS.")

    root_links: list[str] = []
    for path in target.get("required_paths", ["/"]):
        url = urllib.parse.urljoin(base + "/", path.lstrip("/"))
        try:
            status, headers, body, final_url = http.request(url)
        except Exception as exc:
            report.finding("G03", "P0", "UNKNOWN", url, "Required route unavailable",
                           str(exc), "Restore route and rerun.")
            continue
        report.proof("G03", f"GET {path}", target_id, "PASS" if status < 400 else "FAIL",
                     status=status, final_url=final_url, content_type=headers.get("content-type"))
        if status >= 400:
            report.finding("G03", "P0", "FAIL", url, "Required route failed",
                           f"HTTP {status}", "Repair, redirect intentionally, or update the contract.")
            continue
        try:
            head_status, _, _, _ = http.request(url, method="HEAD")
            report.proof("G03", f"HEAD {path}", target_id, "PASS" if head_status < 400 else "FAIL",
                         status=head_status)
            if head_status >= 400:
                report.finding("G03", "P1", "FAIL", url, "HEAD mismatch",
                               f"GET succeeded; HEAD={head_status}", "Implement HEAD or document a tested exception.")
        except Exception as exc:
            report.finding("G03", "P1", "UNKNOWN", url, "HEAD unavailable",
                           str(exc), "Run the contract in a reachable environment.")

        if "text/html" not in headers.get("content-type", ""):
            continue
        text = body.decode("utf-8", errors="replace")
        parser = PageParser()
        parser.feed(text)
        if path == "/":
            root_links = parser.links

        checks = [
            ("document title", bool(parser.title), "G06", "P0"),
            ("HTML language", bool(parser.lang), "G04", "P1"),
            ("viewport metadata", bool(parser.meta.get("viewport")), "G04", "P0"),
            ("meta description", bool(parser.meta.get("description")), "G06", "P1"),
            ("single H1", parser.h1_count == 1, "G04", "P1"),
            ("image alt attributes", parser.images_missing_alt == 0, "G04", "P1"),
            ("button accessible names", parser.unlabelled_buttons == 0, "G04", "P1"),
            ("heading hierarchy", not heading_skip(parser.heading_levels), "G04", "P2"),
        ]
        for control, ok, gate, severity in checks:
            report.proof(gate, control, url, "PASS" if ok else "FAIL")
            if not ok:
                report.finding(
                    gate, severity, "FAIL" if severity in {"P0", "P1"} else "WARN",
                    url, f"HTML control failed: {control}",
                    f"title={parser.title!r}; lang={parser.lang!r}; h1={parser.h1_count}; "
                    f"missing_alt={parser.images_missing_alt}; unnamed_buttons={parser.unlabelled_buttons}",
                    "Correct semantic HTML and add a regression test.",
                    blocking=severity in {"P0", "P1"},
                )
        if parser.canonical:
            canonical_host = urllib.parse.urlparse(
                urllib.parse.urljoin(final_url, parser.canonical)
            ).hostname
            if canonical_host != origin.hostname:
                report.finding("G06", "P1", "FAIL", url, "Canonical origin mismatch",
                               f"{canonical_host!r} != {origin.hostname!r}",
                               "Use the role's declared canonical origin.")
        else:
            report.finding("G06", "P2", "WARN", url, "Canonical link missing",
                           "No rel=canonical observed.", "Add canonical metadata.", blocking=False)

        for phrase in target.get("forbidden_phrases", []):
            if phrase.lower() in text.lower():
                report.finding("G06", "P0", "FAIL", url, "Retired positioning remains public",
                               phrase, "Apply the approved product hierarchy/content contract.")

        for header in target.get("required_security_headers", []):
            ok = bool(headers.get(header.lower()))
            report.proof("G13", f"header:{header.lower()}", url, "PASS" if ok else "FAIL")
            if not ok:
                report.finding("G13", "P1", "FAIL", url, f"Security header missing: {header}",
                               "Header not observed.", "Set it at application or edge and test live.")

        if cookie := headers.get("set-cookie", ""):
            lower = cookie.lower()
            for flag in ("secure", "samesite"):
                if flag not in lower:
                    report.finding("G08", "P1", "FAIL", url, f"Cookie flag missing: {flag}",
                                   "Set-Cookie lacked the flag.", "Apply secure cookie policy.")

    for endpoint in target.get("json_endpoints", []):
        path = endpoint["path"]
        url = urllib.parse.urljoin(base + "/", path.lstrip("/"))
        try:
            status, _, body, _ = http.request(url, headers={"Accept": "application/json"})
            if status >= 400:
                raise ValueError(f"HTTP {status}")
            data = json.loads(body.decode("utf-8"))
            missing = [x for x in endpoint.get("required_fields", []) if x not in data]
            report.proof("G07", f"JSON endpoint {path}", target_id,
                         "PASS" if not missing else "FAIL", missing=missing)
            if missing:
                report.finding("G07", "P0", "FAIL", url, "JSON fields missing",
                               str(missing), "Restore schema and contract tests.")
        except Exception as exc:
            report.finding("G07", "P0", "UNKNOWN", url, "JSON verification unavailable",
                           str(exc), "Repair endpoint/schema and rerun.")

    seen: set[str] = set()
    checked = 0
    for href in root_links:
        if checked >= max_pages:
            break
        absolute = urllib.parse.urljoin(base + "/", href)
        parsed = urllib.parse.urlparse(absolute)
        if parsed.scheme not in {"http", "https"} or parsed.hostname != origin.hostname:
            continue
        normalized = urllib.parse.urlunparse((parsed.scheme, parsed.netloc, parsed.path or "/", "", parsed.query, ""))
        if normalized in seen:
            continue
        seen.add(normalized)
        checked += 1
        try:
            status, _, _, _ = http.request(normalized, method="HEAD")
            if status in {405, 501}:
                status, _, _, _ = http.request(normalized)
            report.proof("G03", "bounded internal link", target_id,
                         "PASS" if status < 400 else "FAIL", url=normalized, status=status)
            if status >= 400:
                report.finding("G03", "P1", "FAIL", normalized, "Broken internal link",
                               f"HTTP {status}", "Repair, redirect, or remove.")
        except Exception as exc:
            report.finding("G03", "P2", "WARN", normalized, "Link check unavailable",
                           str(exc), "Recheck in deployment.", blocking=False)


def iter_files(root: Path, maximum: int = 12000) -> Iterable[Path]:
    count = 0
    for path in root.rglob("*"):
        if count >= maximum:
            break
        if any(part in SKIP_DIRS for part in path.parts):
            continue
        if path.is_file():
            count += 1
            yield path


def text_file(path: Path, limit: int = 1_000_000) -> str | None:
    try:
        if path.stat().st_size > limit:
            return None
        return path.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return None


def audit_workflow(path: Path, text: str, report: Report) -> None:
    for action, ref in ACTION_REF.findall(text):
        if action.startswith("./") or action.startswith("docker://"):
            continue
        if not SHA40.fullmatch(ref):
            report.finding("G13", "P1", "FAIL", str(path), "GitHub Action is not SHA pinned",
                           f"{action}@{ref}", "Pin to a full immutable commit SHA.")
    if re.search(r"^\s*permissions:\s*write-all\s*$", text, re.M):
        report.finding("G13", "P0", "FAIL", str(path), "Workflow grants write-all",
                       "permissions: write-all", "Use minimum literal permissions.")
    if "pull_request_target:" in text:
        report.finding("G13", "P1", "WARN", str(path), "pull_request_target present",
                       "Base-repository privileges can be exposed.",
                       "Prove untrusted PR code is never executed.", blocking=False)
    if re.search(r"continue-on-error:\s*true", text, re.I):
        report.finding("G02", "P1", "WARN", str(path), "Failure masking present",
                       "continue-on-error: true", "Aggregate gates must fail closed.", blocking=False)
    if re.search(r"(?:curl|wget)[^\n|]*\|\s*(?:ba)?sh", text, re.I):
        report.finding("G13", "P0", "FAIL", str(path), "Network pipe to shell",
                       "Downloaded content is piped to a shell.",
                       "Pin, verify, store and execute through an auditable path.")


def audit_docker(path: Path, text: str, report: Report) -> None:
    for line in text.splitlines():
        if line.strip().upper().startswith("FROM "):
            image = line.split()[1]
            if "@sha256:" not in image:
                severity = "P0" if image.endswith(":latest") or ":" not in image else "P1"
                report.finding("G13", severity, "FAIL", str(path),
                               "Container base is not digest pinned", image,
                               "Pin the exact digest and update through review.")
    if not re.search(r"^\s*USER\s+\S+", text, re.M | re.I):
        report.finding("G08", "P1", "WARN", str(path), "Container user not declared",
                       "No USER directive.", "Use a dedicated non-root user or justify.", blocking=False)
    if not re.search(r"^\s*HEALTHCHECK\b", text, re.M | re.I):
        report.finding("G10", "P2", "WARN", str(path), "Container HEALTHCHECK absent",
                       "No HEALTHCHECK directive.", "Add it or document platform probe ownership.", blocking=False)


def audit_repo(repo: dict[str, Any], workspace: Path, report: Report,
               execute_tools: bool, timeout: int) -> None:
    name = repo["repository"]
    short = name.split("/", 1)[1]
    root = workspace / short
    tier = repo.get("production_tier", "T2")
    if not root.exists():
        if tier in {"T0", "T1"}:
            report.finding("G01", "P0" if tier == "T0" else "P1", "UNKNOWN",
                           name, "Local checkout missing", str(root),
                           "Check out the exact revision before local verification.")
        return
    report.proof("G01", "local repository present", name, "PASS", path=str(root))

    required = ["README.md", "LICENSE"]
    if tier == "T0":
        required += ["SECURITY.md", "CONTRIBUTING.md", "CHANGELOG.md"]
    for filename in required:
        if not (root / filename).exists():
            report.finding("G16", "P1", "FAIL", name, f"Required file missing: {filename}",
                           str(root / filename), "Add a current source-bound file.")

    js_locks = [x for x in ("pnpm-lock.yaml", "package-lock.json", "yarn.lock", "bun.lockb") if (root / x).exists()]
    if len(js_locks) > 1:
        report.finding("G01", "P1", "FAIL", name, "Multiple JavaScript lockfiles",
                       str(js_locks), "Select one package manager and remove incompatible locks.")

    package_json = root / "package.json"
    if package_json.exists():
        try:
            package = json.loads(package_json.read_text(encoding="utf-8"))
            scripts = package.get("scripts", {})
            report.proof("G02", "package.json parsed", name, "PASS", scripts=len(scripts))
            for script in ("build", "test"):
                if tier == "T0" and script not in scripts:
                    report.finding("G02", "P1", "FAIL", name, f"Missing package script: {script}",
                                   "T0 JavaScript repo lacks a stable entry point.",
                                   "Add it and include it in production:verify.")
        except Exception as exc:
            report.finding("G01", "P0", "FAIL", str(package_json), "Invalid package.json",
                           str(exc), "Repair package metadata.")

    tests = 0
    scanned = 0
    large: list[dict[str, Any]] = []
    for path in iter_files(root):
        rel = path.relative_to(root)
        if any(part.lower() in {"test", "tests", "__tests__", "spec", "specs"} for part in rel.parts) or re.search(r"(?:test|spec)\.", path.name, re.I):
            tests += 1
        try:
            size = path.stat().st_size
        except OSError:
            continue
        if size > 10 * 1024 * 1024:
            large.append({"path": str(rel), "bytes": size})
        if path.name.lower() == "dockerfile" or path.name.lower().endswith(".dockerfile"):
            if (text := text_file(path)) is not None:
                audit_docker(path, text, report)
            continue
        if path.suffix.lower() not in TEXT_EXTENSIONS:
            continue
        text = text_file(path)
        if text is None:
            continue
        scanned += 1
        for token_name, rx in SECRET_REGEXES:
            if rx.search(text):
                report.finding("G13", "P0", "FAIL", str(rel),
                               f"Credential-like pattern: {token_name}",
                               "Value intentionally redacted.",
                               "Revoke if real, purge safely and enable push protection.")
        for gate, severity, title, rx, detail in CODE_PATTERNS:
            if rx.search(text):
                report.finding(gate, severity, "FAIL" if severity in {"P0", "P1"} else "WARN",
                               str(rel), title, detail,
                               "Review, remove or document exception, and add a focused test.",
                               blocking=severity in {"P0", "P1"})
        if ".github/workflows" in str(rel).replace("\\", "/"):
            audit_workflow(path, text, report)
        if path.name.startswith("requirements") and path.suffix in {".txt", ".in"}:
            for line in text.splitlines():
                item = line.strip()
                if item and not item.startswith(("#", "-", "http")) and "==" not in item and " @ " not in item:
                    report.finding("G01", "P1", "WARN", str(rel), "Unpinned Python dependency",
                                   item.split(";", 1)[0], "Use exact/hash-locked dependencies.", blocking=False)

    report.proof("G02", "source scan completed", name, "PASS",
                 text_files_scanned=scanned, test_files=tests)
    if tier in {"T0", "T1"} and tests == 0:
        report.finding("G02", "P0" if tier == "T0" else "P1", "FAIL",
                       name, "No tests discovered", "Bounded scan found no tests.",
                       "Add risk-focused unit, contract, integration and journey tests.")
    if large:
        report.finding("G01", "P1", "WARN", name, "Large Git files detected",
                       f"{len(large)} files exceed 10 MiB.",
                       "Move generated/binary artifacts to governed storage or Git LFS.",
                       blocking=False, evidence={"sample": large[:20]})

    if (root / ".git").exists() and shutil.which("git"):
        proc = subprocess.run(["git", "-C", str(root), "status", "--porcelain=v1"],
                              capture_output=True, text=True, timeout=30)
        dirty = bool(proc.stdout.strip())
        report.proof("G01", "clean working tree", name, "PASS" if not dirty else "FAIL", dirty=dirty)
        if dirty:
            report.finding("G01", "P1", "FAIL", name, "Working tree is dirty",
                           "Production evidence requires a clean exact tree.",
                           "Commit, stash or discard unrelated changes.")

    if execute_tools:
        for command in report.profile.get("repo_commands", {}).get(name, []):
            if not shutil.which(command[0]):
                report.finding("G02", "P1", "UNKNOWN", name, f"Tool unavailable: {command[0]}",
                               "Configured verification could not run.",
                               "Use the locked CI/toolchain environment.")
                continue
            started = time.monotonic()
            try:
                proc = subprocess.run(command, cwd=root, capture_output=True, text=True,
                                      timeout=timeout, env={**os.environ, "CI": "1"})
                elapsed = round(time.monotonic() - started, 3)
                status = "PASS" if proc.returncode == 0 else "FAIL"
                report.proof("G02", "local command", name, status, command=command,
                             exit_code=proc.returncode, elapsed_seconds=elapsed,
                             stdout=redact(proc.stdout[-4000:]),
                             stderr=redact(proc.stderr[-4000:]))
                if proc.returncode:
                    report.finding("G02", "P0" if tier == "T0" else "P1", "FAIL",
                                   name, "Verification command failed",
                                   f"{shlex.join(command)} exited {proc.returncode}",
                                   "Fix the first causal failure and retain a debug bundle.")
            except subprocess.TimeoutExpired:
                report.finding("G02", "P1", "FAIL", name, "Verification timed out",
                               shlex.join(command),
                               "Remove hangs, split the gate, or use an evidence-based timeout.")


def gh_json(http: HTTP, path: str, token: str | None) -> Any:
    url = path if path.startswith("https://") else "https://api.github.com" + path
    return http.json(url, token=token)


def audit_github(profile: dict[str, Any], report: Report, http: HTTP) -> None:
    token = os.environ.get("GH_TOKEN") or os.environ.get("GITHUB_TOKEN")
    org = "szl-holdings"
    try:
        repos = gh_json(http, f"/orgs/{org}/repos?per_page=100&type=all", token)
        if not isinstance(repos, list):
            raise ValueError("repo response is not a list")
        report.proof("G00", "GitHub repository inventory", org, "PASS", count=len(repos))
        if len(repos) != len(profile["repositories"]):
            report.finding("G00", "P0", "FAIL", org, "Repository inventory drift",
                           f"profile={len(profile['repositories'])}; api={len(repos)}",
                           "Recapture and classify every asset.")
    except Exception as exc:
        report.finding("G00", "P0", "UNKNOWN", org, "GitHub inventory unavailable",
                       str(exc), "Provide read-only metadata access and rerun.")
        return

    try:
        query = urllib.parse.quote(f"org:{org} is:pr is:open")
        issues = gh_json(http, f"/search/issues?q={query}&per_page=100", token)
        report.proof("G00", "Open PR inventory", org, "PASS",
                     count=int(issues.get("total_count", 0)))
    except Exception as exc:
        report.finding("G00", "P1", "UNKNOWN", org, "Open PR inventory unavailable",
                       str(exc), "Recapture before promotion.")

    for repo in profile["repositories"]:
        if repo.get("production_tier") not in {"T0", "T1"}:
            continue
        name = repo["repository"]
        try:
            meta = gh_json(http, f"/repos/{name}", token)
            report.proof("G00", "repository settings", name, "PASS",
                         default_branch=meta.get("default_branch"),
                         archived=meta.get("archived"),
                         allow_squash=meta.get("allow_squash_merge"),
                         allow_rebase=meta.get("allow_rebase_merge"),
                         allow_merge=meta.get("allow_merge_commit"))
            if meta.get("allow_rebase_merge") or meta.get("allow_merge_commit"):
                report.finding("G00", "P1", "FAIL", name, "Non-squash merge method enabled",
                               f"rebase={meta.get('allow_rebase_merge')}; merge={meta.get('allow_merge_commit')}",
                               "Use squash-only protected promotion for the production profile.")
        except Exception as exc:
            report.finding("G00", "P1", "UNKNOWN", name, "Repository settings unavailable",
                           str(exc), "Restore metadata access.")

        try:
            summaries = gh_json(http, f"/repos/{name}/rulesets", token)
            approvals = 0
            checks: set[str] = set()
            workflows: list[str] = []
            signatures = False
            strict = False
            bypass = 0
            for summary in summaries:
                if summary.get("target") != "branch" or summary.get("enforcement") != "active":
                    continue
                detail = gh_json(http, f"/repos/{name}/rulesets/{summary['id']}", token)
                bypass += len(detail.get("bypass_actors", []))
                for rule in detail.get("rules", []):
                    rtype, params = rule.get("type"), rule.get("parameters", {})
                    if rtype == "pull_request":
                        approvals = max(approvals, int(params.get("required_approving_review_count", 0)))
                    elif rtype == "required_status_checks":
                        strict = strict or bool(params.get("strict_required_status_checks_policy"))
                        checks |= {x.get("context", "") for x in params.get("required_status_checks", [])}
                    elif rtype == "required_signatures":
                        signatures = True
                    elif rtype == "workflows":
                        workflows += [x.get("path", "") for x in params.get("workflows", [])]
            report.proof("G00", "effective ruleset snapshot", name, "PASS",
                         approvals=approvals, checks=sorted(checks), workflows=workflows,
                         signatures=signatures, strict=strict, bypass_actors=bypass)
            expected = (
                {"gitleaks", "lockfile", "ci", "e2e", "security", "codeql", "dependency", "readiness"}
                if repo["production_tier"] == "T0" else {"gitleaks", "security", "dependency"}
            )
            text = " ".join(checks | set(workflows)).lower()
            missing = sorted(x for x in expected if x not in text)
            if missing:
                report.finding("G00", "P0" if repo["production_tier"] == "T0" else "P1",
                               "FAIL", name, "Production checks are not enforced",
                               f"missing={missing}; checks={sorted(checks)}; workflows={workflows}",
                               "Discover exact check names, require them, and verify via API readback.")
            if not strict:
                report.finding("G00", "P0", "FAIL", name, "Checks are not strict/up-to-date",
                               "No active strict status-check rule observed.",
                               "Require candidate head current with protected main.")
            if bypass:
                report.finding("G00", "P0", "FAIL", name, "Ruleset bypass actor exists",
                               str(bypass), "Remove or narrowly govern break-glass access.")
            if not signatures:
                report.finding("G00", "P1", "FAIL", name, "Required signatures absent",
                               "No active required_signatures rule observed.",
                               "Require signed production commits.")
        except Exception as exc:
            report.finding("G00", "P0" if repo["production_tier"] == "T0" else "P1",
                           "UNKNOWN", name, "Ruleset readback unavailable",
                           str(exc), "Use read-only ruleset metadata access and rerun.")


def hf_list(http: HTTP, kind: str, token: str | None) -> list[dict[str, Any]]:
    endpoint = {"models": "models", "datasets": "datasets", "spaces": "spaces"}[kind]
    url = f"https://huggingface.co/api/{endpoint}?author=SZLHOLDINGS&limit=100&full=true"
    data = http.json(url, token=token)
    if not isinstance(data, list):
        raise ValueError(f"{kind} response is not a list")
    return data


def audit_hf(report: Report, http: HTTP) -> None:
    token = os.environ.get("HF_TOKEN")
    inventory: dict[str, list[dict[str, Any]]] = {}
    for kind in ("models", "datasets", "spaces"):
        try:
            inventory[kind] = hf_list(http, kind, token)
            report.proof("G15", f"HF {kind} inventory", "SZLHOLDINGS", "PASS",
                         count=len(inventory[kind]))
        except Exception as exc:
            inventory[kind] = []
            report.finding("G15", "P0", "UNKNOWN", "SZLHOLDINGS",
                           f"HF {kind} inventory unavailable", str(exc),
                           "Restore read access and recapture exact inventory.")

    for item in inventory["models"]:
        model_id = item.get("id") or item.get("modelId") or "UNKNOWN"
        siblings = item.get("siblings") or []
        names = [x.get("rfilename", "") if isinstance(x, dict) else str(x) for x in siblings]
        unsafe = [x for x in names if Path(x).suffix.lower() in UNSAFE_SERIALIZATION_EXTENSIONS]
        weights = [x for x in names if Path(x).suffix.lower() in WEIGHT_EXTENSIONS]
        card = item.get("cardData") or {}
        report.proof("G15", "HF model inspected", model_id, "PASS",
                     unsafe_files=unsafe, weight_files=weights[:50],
                     license=card.get("license"), pipeline_tag=item.get("pipeline_tag"))
        if unsafe:
            report.finding("G15", "P0", "FAIL", model_id,
                           "Unsafe executable serialization on Hub", str(unsafe),
                           "Delete/quarantine through exact-parent Hub PR and publish a safe successor/revocation.")
        if not card.get("license"):
            report.finding("G15", "P1", "FAIL", model_id, "License metadata missing",
                           "cardData.license absent.", "Add valid license or keep unavailable/private.")
        if not weights and item.get("pipeline_tag"):
            report.finding("G15", "P1", "WARN", model_id,
                           "Task metadata without observed weights",
                           f"pipeline_tag={item.get('pipeline_tag')}",
                           "Remove misleading inference metadata or publish exact weight lineage.",
                           blocking=False)

    for item in inventory["spaces"]:
        space_id = item.get("id") or "UNKNOWN"
        runtime = item.get("runtime") or {}
        stage = runtime.get("stage") or item.get("stage") or "UNKNOWN"
        report.proof("G15", "HF Space inspected", space_id, "PASS",
                     stage=stage, sdk=item.get("sdk"), sha=item.get("sha"))
        if stage not in {"RUNNING", "RUNNING_BUILDING"}:
            report.finding("G15", "P1", "WARN", space_id, "Space is not running",
                           f"stage={stage}", "Repair, archive, or label honestly.", blocking=False)


def write_outputs(report: Report, out: Path, profile_path: Path) -> tuple[dict[str, Any], int]:
    gates = report.gate_results()
    if any(x["blocking"] and x["status"] == "FAIL" for x in report.findings):
        overall, code = "BLOCKED", 2
    elif any(x["blocking"] and x["status"] in {"UNKNOWN", "UNAVAILABLE"} for x in report.findings) or any(
        x["block_release"] and x["status"] != "PASS" for x in gates
    ):
        overall, code = "NOT_VERIFIED", 2
    elif any(x["status"] == "WARN" for x in report.findings):
        overall, code = "PASS_WITH_WARNINGS", 1
    else:
        overall, code = "VERIFIED_PRODUCTION_READY", 0

    result = {
        "schema": "szl.production-readiness-report/v5",
        "generated_at": now(), "auditor_version": VERSION,
        "profile_sha256": file_hash(profile_path),
        "overall_status": overall, "gates": gates,
        "findings": report.findings, "evidence": report.evidence,
        "truth_boundary": "External behavior was read-only; missing evidence is not a pass.",
    }
    out.mkdir(parents=True, exist_ok=True)
    (out / "production_readiness.json").write_bytes(canonical_json(result))

    fields = ["finding_id", "gate_id", "severity", "status", "blocking",
              "target", "title", "detail", "remediation"]
    with (out / "findings.csv").open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=fields, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(result["findings"])

    lines = [
        "# SZL Production Readiness Report", "",
        f"- Generated: {result['generated_at']}",
        f"- Overall: **{overall}**",
        f"- Findings: {len(result['findings'])}", "",
        "## Gates", "",
        "| Gate | Domain | Priority | Status | Findings | Evidence |",
        "|---|---|---:|---|---:|---:|",
    ]
    for gate in gates:
        lines.append(
            f"| {gate['id']} — {gate['name']} | {gate['domain']} | "
            f"{gate['priority']} | {gate['status']} | "
            f"{gate['finding_count']} | {gate['evidence_count']} |"
        )
    lines += ["", "## Findings", ""]
    for item in result["findings"]:
        lines += [
            f"### {item['finding_id']} · {item['severity']} · {item['status']} · {item['title']}",
            f"- Gate: `{item['gate_id']}`",
            f"- Target: `{item['target']}`",
            f"- Blocking: `{item['blocking']}`",
            f"- Detail: {item['detail']}",
            f"- Remediation: {item['remediation']}", "",
        ]
    (out / "PRODUCTION_READINESS_REPORT.md").write_text("\n".join(lines) + "\n", encoding="utf-8")

    suite = ET.Element("testsuite", {
        "name": "szl-production-readiness", "tests": str(len(gates)),
        "failures": str(sum(x["status"] == "FAIL" for x in gates)),
        "errors": str(sum(x["status"] in {"UNKNOWN", "PARTIAL"} for x in gates)),
    })
    for gate in gates:
        case = ET.SubElement(suite, "testcase", {"classname": gate["domain"], "name": gate["id"]})
        if gate["status"] == "FAIL":
            ET.SubElement(case, "failure", {"message": gate["name"]})
        elif gate["status"] in {"UNKNOWN", "PARTIAL"}:
            ET.SubElement(case, "error", {"message": gate["status"]})
    ET.ElementTree(suite).write(out / "junit.xml", encoding="utf-8", xml_declaration=True)

    rules, sarif_results = {}, []
    for item in result["findings"]:
        rid = f"{item['gate_id']}/{re.sub(r'[^A-Za-z0-9._-]+','-',item['title'])[:70]}"
        rules[rid] = {"id": rid, "shortDescription": {"text": item["title"]},
                      "help": {"text": item["remediation"]}}
        sarif_results.append({
            "ruleId": rid,
            "level": "error" if item["severity"] in {"P0", "P1"} else "warning",
            "message": {"text": f"{item['target']}: {item['detail']}"},
        })
    sarif = {
        "$schema": "https://json.schemastore.org/sarif-2.1.0.json",
        "version": "2.1.0",
        "runs": [{"tool": {"driver": {"name": "SZL Production Auditor",
                                     "version": VERSION,
                                     "rules": list(rules.values())}},
                  "results": sarif_results}],
    }
    (out / "findings.sarif").write_bytes(canonical_json(sarif))

    receipt = {
        "schema": "szl.production-audit-receipt/v5",
        "generated_at": now(), "auditor_version": VERSION,
        "read_only_external": True,
        "profile": {"path": str(profile_path), "sha256": file_hash(profile_path)},
        "overall_status": overall, "outputs": {},
    }
    for path in sorted(out.iterdir()):
        if path.is_file() and path.name != "run_receipt.json":
            receipt["outputs"][path.name] = {
                "sha256": file_hash(path), "bytes": path.stat().st_size
            }
    (out / "run_receipt.json").write_bytes(canonical_json(receipt))
    return result, code


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Read-only SZL production-readiness auditor")
    parser.add_argument("--profile", type=Path, default=Path("szl_production_readiness_profile_v5.json"))
    parser.add_argument("--workspace", type=Path, default=Path.cwd())
    parser.add_argument("--out", type=Path, default=Path("production-readiness-output"))
    parser.add_argument("--offline", action="store_true")
    parser.add_argument("--skip-web", action="store_true")
    parser.add_argument("--skip-github", action="store_true")
    parser.add_argument("--skip-hf", action="store_true")
    parser.add_argument("--execute-tools", action="store_true")
    parser.add_argument("--tool-timeout", type=int, default=1800)
    parser.add_argument("--max-pages", type=int, default=30)
    parser.add_argument("--validate-only", action="store_true")
    args = parser.parse_args(argv)

    try:
        profile = json.loads(args.profile.read_text(encoding="utf-8"))
        errors = validate_profile(profile)
        if errors:
            for error in errors:
                print(f"ERROR: {error}", file=sys.stderr)
            return 3
        print("VALID")
        if args.validate_only:
            return 0

        report = Report(profile)
        http = HTTP()
        for repo in profile["repositories"]:
            if repo.get("production_tier") in {"T0", "T1"}:
                audit_repo(repo, args.workspace, report, args.execute_tools, args.tool_timeout)

        if args.offline:
            for gate, title in (
                ("G03", "Web audit skipped offline"),
                ("G00", "GitHub audit skipped offline"),
                ("G15", "Hugging Face audit skipped offline"),
            ):
                report.finding(gate, "P0", "UNKNOWN", "external", title,
                               "--offline was used.", "Rerun with network before release.")
        else:
            if not args.skip_web:
                with ThreadPoolExecutor(max_workers=min(6, len(profile["web_targets"]) or 1)) as pool:
                    futures = {pool.submit(audit_web, target, http, report, args.max_pages): target["id"]
                               for target in profile["web_targets"]}
                    for future in as_completed(futures):
                        try:
                            future.result()
                        except Exception as exc:
                            report.finding("G03", "P0", "UNKNOWN", futures[future],
                                           "Web audit crashed", str(exc), "Fix and rerun.")
            if not args.skip_github:
                audit_github(profile, report, http)
            if not args.skip_hf:
                audit_hf(report, http)

        result, code = write_outputs(report, args.out, args.profile)
        print(json.dumps({
            "overall_status": result["overall_status"],
            "findings": len(result["findings"]),
            "gates": {x["id"]: x["status"] for x in result["gates"]},
            "output": str(args.out),
        }, indent=2, sort_keys=True))
        return code
    except Exception as exc:
        print(f"FATAL: {redact(str(exc))}", file=sys.stderr)
        return 3


if __name__ == "__main__":
    raise SystemExit(main())
