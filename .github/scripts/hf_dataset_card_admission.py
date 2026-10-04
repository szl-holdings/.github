#!/usr/bin/env python3
"""Validate two source-only dataset card proposals; no provider effects."""
import argparse
import hashlib
import json
from pathlib import Path, PurePosixPath
import re
import stat
import sys


MANIFEST_PATH = "huggingface/dataset-cards/admission.json"
SCHEMA = "szl.hf-dataset-card-admission/v1"
GOVERNANCE_BASE = "9887bc1716f5ee1dc0642a7310c1d8779acee59e"
MAX_MANIFEST_BYTES = 65536
MAX_CARD_BYTES = 16384
SHA256 = re.compile(r"[0-9a-f]{64}\Z")
GIT_OID = re.compile(r"[0-9a-f]{40}\Z")
REPARSE_POINT = getattr(stat, "FILE_ATTRIBUTE_REPARSE_POINT", 0x400)

# These anchors describe the independently read immutable Hub snapshots. A
# future baseline needs a separately reviewed source change, not a nearby rehash.
ANCHORS = {
    "SZLHOLDINGS/test-results": {
        "revision": "4d5de7b588460f56fc67437b11617c339a69d8c8",
        "before_sha256": "f881406b4521d8402d294e237018e8a7abaf8579d838ca61ffa4999c636ec4c3",
        "before_oid": "73fcefbd39f336beea48544c42bc690fc4743c5f",
        "before_size": 3480,
        "retained_count": 14,
        "retained_sha256": "42ff883d40f3bd6d14ffe1e45a31edc37c3a2f0af9bf4586ec4067f0db019dba",
        "change": "select-harness-runs",
        "anchor": "pretty_name: SZL test-results — anatomy alive-harness runs (DSSE-signed)\n".encode(),
        "insertion": b"configs:\n- config_name: default\n  data_files:\n  - split: train\n    path: harness_runs.jsonl\n",
    },
    "SZLHOLDINGS/SZLHOLDINGS": {
        "revision": "7a6cce17710bf47b9e5a64e0b1be43d1276733ef",
        "before_sha256": "d649056402f1fbe4e9764cfaaa8161c60b4847bb226dfb5e61af9fde85fbbed1",
        "before_oid": "97c0fb57d3bcd5689e6d941a6b463261e8499107",
        "before_size": 4349,
        "retained_count": 6,
        "retained_sha256": "b63025760ea921be2f7a9b9027029063ac5797c8c3f8eb1dc9456b77259006fd",
        "change": "disable-metadata-viewer",
        "anchor": b"---\n",
        "insertion": b"viewer: false\n",
    },
}


class AdmissionError(ValueError):
    """The local source proposal differs from its bounded admission contract."""


def require(condition, message):
    if not condition:
        raise AdmissionError(message)


def sha256(data):
    return hashlib.sha256(data).hexdigest()


def canonical(data):
    return json.dumps(data, sort_keys=True, separators=(",", ":")).encode("utf-8")


def exact_keys(value, keys, label):
    require(type(value) is dict and set(value) == set(keys), label + ": invalid fields")


def relative_path(value):
    require(type(value) is str and bool(value), "invalid relative path")
    require("\\" not in value and ":" not in value, "nonportable relative path")
    require(not any(ord(char) < 32 or ord(char) == 127 for char in value), "control character in path")
    path = PurePosixPath(value)
    require(not path.is_absolute() and path.as_posix() == value, "noncanonical relative path")
    require(all(part not in (".", "..") for part in path.parts), "unsafe relative path")
    require(all(not part.endswith((".", " ")) for part in path.parts), "nonportable path component")
    return path


def read_regular(root, relative, limit):
    path = relative_path(relative)
    current = root
    for index, part in enumerate(("", *path.parts)):
        if part:
            current = current / part
        info = current.lstat()
        require(not stat.S_ISLNK(info.st_mode), "symbolic link refused")
        require(not getattr(info, "st_file_attributes", 0) & REPARSE_POINT, "reparse point refused")
        if index < len(path.parts):
            require(stat.S_ISDIR(info.st_mode), "parent is not a directory")
        else:
            require(stat.S_ISREG(info.st_mode), "input is not a regular file")
            require(info.st_size <= limit, "input byte limit exceeded")
    with current.open("rb") as handle:
        data = handle.read(limit + 1)
    require(len(data) <= limit, "input byte limit exceeded")
    return data


def unique_object(pairs):
    result = {}
    for key, value in pairs:
        require(key not in result, "duplicate JSON key")
        result[key] = value
    return result


def reject_constant(_value):
    raise AdmissionError("nonfinite JSON value")


def validate(root):
    """Read only the fixed manifest and two candidate cards, without execution."""
    root = Path(root).absolute()
    raw = read_regular(root, MANIFEST_PATH, MAX_MANIFEST_BYTES)
    manifest = json.loads(raw, object_pairs_hook=unique_object, parse_constant=reject_constant)
    exact_keys(manifest, {
        "schema", "scope", "proposed_source_repository", "proposal_governance_base",
        "authority_status", "effects_allowed", "provider_publication", "targets",
    }, "manifest")
    require(manifest["schema"] == SCHEMA, "unexpected schema")
    require(manifest["scope"] == "source-only", "not a source-only proposal")
    require(manifest["proposed_source_repository"] == "szl-holdings/.github", "unexpected source repository")
    require(manifest["proposal_governance_base"] == GOVERNANCE_BASE, "governance base changed")
    require(manifest["authority_status"] == "PENDING_PROTECTED_OWNER_MERGE", "authority is not pending")
    require(manifest["effects_allowed"] is False, "provider effects refused")
    require(manifest["provider_publication"] == "NOT_ATTEMPTED", "publication claim refused")
    targets = manifest["targets"]
    require(type(targets) is list and len(targets) == len(ANCHORS), "complete two-target admission required")
    seen, measured = set(), []
    for target in targets:
        exact_keys(target, {
            "repo_id", "repo_type", "observed_hub_revision", "observed_readme", "change",
            "candidate_path", "candidate_sha256", "candidate_size_bytes",
            "retained_files", "retained_files_sha256",
        }, "target")
        repo_id = target["repo_id"]
        require(type(repo_id) is str and repo_id in ANCHORS and repo_id not in seen, "unknown or duplicate target")
        seen.add(repo_id)
        anchor = ANCHORS[repo_id]
        require(target["repo_type"] == "dataset", "non-dataset identity refused")
        require(target["observed_hub_revision"] == anchor["revision"], "immutable Hub revision changed")
        require(target["change"] == anchor["change"], "undeclared card operation")
        before = target["observed_readme"]
        exact_keys(before, {"path", "git_blob_oid", "sha256", "size_bytes"}, "observed card")
        require(before["path"] == "README.md", "unexpected observed card path")
        require(before["git_blob_oid"] == anchor["before_oid"], "observed card Git blob changed")
        require(before["sha256"] == anchor["before_sha256"], "observed card digest changed")
        require(type(before["size_bytes"]) is int and before["size_bytes"] == anchor["before_size"], "observed card size changed")
        expected_path = "huggingface/dataset-cards/" + repo_id + "/README.md"
        require(target["candidate_path"] == expected_path, "candidate path differs from exact target")
        candidate = read_regular(root, target["candidate_path"], MAX_CARD_BYTES)
        require(type(target["candidate_sha256"]) is str and SHA256.fullmatch(target["candidate_sha256"]), "invalid candidate digest")
        require(sha256(candidate) == target["candidate_sha256"], "candidate byte drift")
        require(type(target["candidate_size_bytes"]) is int and len(candidate) == target["candidate_size_bytes"], "candidate size drift")
        combined = anchor["anchor"] + anchor["insertion"]
        require(candidate.count(combined) == 1, "missing or repeated permitted insertion")
        if anchor["change"] == "disable-metadata-viewer":
            require(candidate.startswith(combined), "viewer declaration is not front matter")
        restored = candidate.replace(combined, anchor["anchor"], 1)
        require(len(restored) == anchor["before_size"] and sha256(restored) == anchor["before_sha256"], "card changes exceed the reviewed insertion")
        retained = target["retained_files"]
        require(type(retained) is list and len(retained) == anchor["retained_count"], "retained manifest is incomplete")
        paths = []
        for item in retained:
            exact_keys(item, {"path", "git_blob_oid", "size_bytes"}, "retained file")
            relative_path(item["path"])
            require(item["path"] != "README.md", "changed card included in retained manifest")
            require(type(item["git_blob_oid"]) is str and GIT_OID.fullmatch(item["git_blob_oid"]), "invalid retained Git blob")
            require(type(item["size_bytes"]) is int and 0 <= item["size_bytes"] <= 1048576, "invalid retained byte count")
            paths.append(item["path"])
        require(paths == sorted(set(paths)), "retained paths must be unique and sorted")
        retained_hash = sha256(canonical(retained))
        require(target["retained_files_sha256"] == anchor["retained_sha256"] == retained_hash, "retained immutable manifest drift")
        measured.append({"repo_id": repo_id, "hub_revision": anchor["revision"],
                         "candidate_sha256": sha256(candidate), "baseline_hash_restored": True,
                         "retained_non_readme_files": len(retained)})
    require(seen == set(ANCHORS), "complete two-target admission required")
    return {"schema": "szl.hf-dataset-card-admission-check/v1", "status": "PASS",
            "evidence_class": "MEASURED", "scope": "local candidate bytes and declared immutable manifests",
            "manifest_sha256": sha256(raw), "authority_status": "PENDING_PROTECTED_OWNER_MERGE",
            "effects_allowed": False, "provider_publication": "NOT_ATTEMPTED",
            "provider_readback": "NOT_RUN", "signature_verification": "NOT_RUN",
            "scientific_validity": "UNKNOWN", "targets": measured}


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", default=str(Path(__file__).resolve().parents[2]))
    args = parser.parse_args(argv)
    try:
        report = validate(args.root)
    except (ValueError, OSError, RecursionError):
        print(json.dumps({"status": "BLOCKED", "error": "DATASET_CARD_ADMISSION_INVALID",
                          "effects_allowed": False, "provider_publication": "NOT_ATTEMPTED"}))
        return 2
    print(json.dumps(report, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
