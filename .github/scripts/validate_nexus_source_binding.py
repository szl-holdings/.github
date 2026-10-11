#!/usr/bin/env python3
# Copyright 2026 SZL Holdings - SPDX-License-Identifier: Apache-2.0
"""Validate the exact Docker COPY that binds a NEXUS image to Git source."""

from __future__ import annotations

import argparse
import json
import os
import re
import shlex
import stat
import sys
from dataclasses import asdict, dataclass
from pathlib import Path, PurePosixPath
from typing import Iterator, Sequence

SCHEMA = "szl.nexus-source-binding/v1"
MAX_DOCKERFILE_BYTES = 1_048_576
_SOURCE = "SOURCE_GITHUB_SHA"
_ASSIGNMENT_OPTIONS = {"chown", "chmod"}
_BOOLEAN_OPTIONS = {"link", "parents"}
_COPY_RE = re.compile(r"^COPY\s+(.+)$", re.IGNORECASE)


class SourceBindingError(ValueError):
    """Raised when the reviewed Docker source-binding grammar is not met."""


@dataclass(frozen=True)
class SourceBinding:
    line: int
    options: tuple[str, ...]
    source: str
    destination: str


def _read_bounded_regular_file(path: Path) -> str:
    try:
        before = path.lstat()
    except OSError as exc:
        raise SourceBindingError(f"cannot stat Dockerfile: {exc}") from exc
    if stat.S_ISLNK(before.st_mode) or not stat.S_ISREG(before.st_mode):
        raise SourceBindingError("Dockerfile must be a regular non-symlink file")
    if before.st_size > MAX_DOCKERFILE_BYTES:
        raise SourceBindingError("Dockerfile exceeds the reviewed size bound")

    flags = os.O_RDONLY | getattr(os, "O_BINARY", 0)
    if hasattr(os, "O_NOFOLLOW"):
        flags |= os.O_NOFOLLOW
    try:
        descriptor = os.open(path, flags)
    except OSError as exc:
        raise SourceBindingError(f"cannot open Dockerfile safely: {exc}") from exc
    try:
        opened = os.fstat(descriptor)
        if not stat.S_ISREG(opened.st_mode):
            raise SourceBindingError("opened Dockerfile is not regular")
        if (opened.st_dev, opened.st_ino) != (before.st_dev, before.st_ino):
            raise SourceBindingError("Dockerfile changed while it was being opened")
        chunks: list[bytes] = []
        total = 0
        while True:
            chunk = os.read(descriptor, min(65_536, MAX_DOCKERFILE_BYTES + 1 - total))
            if not chunk:
                break
            chunks.append(chunk)
            total += len(chunk)
            if total > MAX_DOCKERFILE_BYTES:
                raise SourceBindingError("Dockerfile exceeds the reviewed size bound")
        after = os.fstat(descriptor)
        if (
            (after.st_dev, after.st_ino) != (opened.st_dev, opened.st_ino)
            or after.st_size != opened.st_size
            or after.st_mtime_ns != opened.st_mtime_ns
        ):
            raise SourceBindingError("Dockerfile changed while it was being read")
        raw = b"".join(chunks)
    finally:
        os.close(descriptor)
    try:
        return raw.decode("utf-8")
    except UnicodeDecodeError as exc:
        raise SourceBindingError("Dockerfile must be strict UTF-8") from exc


def _has_continuation(line: str) -> bool:
    stripped = line.rstrip()
    trailing = len(stripped) - len(stripped.rstrip("\\"))
    return trailing % 2 == 1


def logical_instructions(text: str) -> Iterator[tuple[int, str]]:
    parts: list[str] = []
    start = 0
    for number, raw in enumerate(text.splitlines(), start=1):
        stripped = raw.strip()
        if not parts and (not stripped or stripped.startswith("#")):
            continue
        if not parts:
            start = number
        continued = _has_continuation(raw)
        piece = stripped[:-1].rstrip() if continued else stripped
        if piece:
            parts.append(piece)
        if continued:
            continue
        if parts:
            yield start, " ".join(parts)
        parts = []
        start = 0
    if parts:
        raise SourceBindingError(
            f"unterminated Dockerfile continuation beginning at line {start}"
        )


def _valid_destination(destination: str) -> bool:
    if destination in {".", "./"}:
        return True
    normalized = destination.replace("\\", "/").rstrip("/")
    return bool(normalized) and PurePosixPath(normalized).name == _SOURCE


def _parse_candidate(line: int, body: str) -> SourceBinding | None:
    if body.lstrip().startswith("["):
        raise SourceBindingError(
            f"line {line}: JSON-form COPY is outside the reviewed binding grammar"
        )
    try:
        tokens = shlex.split(body, posix=True, comments=False)
    except ValueError as exc:
        raise SourceBindingError(f"line {line}: invalid COPY quoting: {exc}") from exc

    options: list[str] = []
    while tokens and tokens[0].startswith("--"):
        option = tokens.pop(0)
        name, separator, value = option[2:].partition("=")
        if name == "from":
            if _SOURCE in body:
                raise SourceBindingError(
                    f"line {line}: --from cannot prove a build-context source binding"
                )
            return None
        if name in _ASSIGNMENT_OPTIONS:
            if not separator or not value:
                raise SourceBindingError(
                    f"line {line}: --{name} requires a non-empty inline value"
                )
        elif name in _BOOLEAN_OPTIONS:
            if separator:
                raise SourceBindingError(
                    f"line {line}: --{name} is a reviewed boolean option"
                )
        else:
            if _SOURCE in body:
                raise SourceBindingError(
                    f"line {line}: unreviewed COPY option --{name or '<empty>'}"
                )
            return None
        options.append(option)

    if _SOURCE not in tokens:
        return None
    if len(tokens) != 2:
        raise SourceBindingError(
            f"line {line}: source binding COPY must have exactly one source and one destination"
        )
    source, destination = tokens
    if source != _SOURCE:
        raise SourceBindingError(
            f"line {line}: wildcard or transformed source cannot prove exact binding"
        )
    if not _valid_destination(destination):
        raise SourceBindingError(
            f"line {line}: destination must preserve the SOURCE_GITHUB_SHA filename"
        )
    return SourceBinding(
        line=line,
        options=tuple(options),
        source=source,
        destination=destination,
    )


def inspect_dockerfile_text(text: str) -> SourceBinding:
    bindings: list[SourceBinding] = []
    for line, instruction in logical_instructions(text):
        match = _COPY_RE.fullmatch(instruction)
        if not match:
            continue
        candidate = _parse_candidate(line, match.group(1))
        if candidate is not None:
            bindings.append(candidate)
    if not bindings:
        raise SourceBindingError(
            "Dockerfile has no exact build-context COPY for SOURCE_GITHUB_SHA"
        )
    if len(bindings) != 1:
        raise SourceBindingError(
            f"Dockerfile must contain exactly one source binding; found {len(bindings)}"
        )
    return bindings[0]


def inspect_dockerfile(path: Path) -> SourceBinding:
    return inspect_dockerfile_text(_read_bounded_regular_file(path))


def build_report(path: Path, binding: SourceBinding) -> dict[str, object]:
    return {
        "schema": SCHEMA,
        "binding": True,
        "dockerfile": path.as_posix(),
        **asdict(binding),
    }


def _write_report_exclusive(path: Path, encoded: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL | getattr(os, "O_BINARY", 0)
    if hasattr(os, "O_NOFOLLOW"):
        flags |= os.O_NOFOLLOW
    try:
        descriptor = os.open(path, flags, 0o600)
    except OSError as exc:
        raise SourceBindingError(f"cannot create evidence report exclusively: {exc}") from exc
    try:
        data = encoded.encode("utf-8")
        view = memoryview(data)
        while view:
            written = os.write(descriptor, view)
            if written <= 0:
                raise SourceBindingError("short write while creating evidence report")
            view = view[written:]
        os.fsync(descriptor)
    finally:
        os.close(descriptor)


def parse_args(argv: Sequence[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("dockerfile", type=Path)
    parser.add_argument("--report", type=Path)
    return parser.parse_args(argv)


def main(argv: Sequence[str] | None = None) -> int:
    args = parse_args(argv)
    try:
        binding = inspect_dockerfile(args.dockerfile)
    except SourceBindingError as exc:
        print(f"Nexus source binding denied: {exc}", file=sys.stderr)
        return 1
    report = build_report(args.dockerfile, binding)
    encoded = json.dumps(report, indent=2, sort_keys=True) + "\n"
    if args.report is not None:
        try:
            _write_report_exclusive(args.report, encoded)
        except SourceBindingError as exc:
            print(f"Nexus source-binding evidence denied: {exc}", file=sys.stderr)
            return 1
    print(json.dumps(report, sort_keys=True, separators=(",", ":")))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
