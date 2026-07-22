#!/usr/bin/env python3
"""Finalize merged SZLHOLDINGS Hugging Face releases with fail-closed evidence.

This release lane performs only three bounded publications:

* ``szl-holdings/szl-lake`` -> ``SZLHOLDINGS/szl-lake`` dataset card and data;
* ``szl-holdings/szl-energy-attest`` -> the existing first-class
  ``SZLHOLDINGS/governed-inference-meter`` kernel card/contract;
* ``szl-holdings/szl-lambda-gate`` -> the existing first-class
  ``SZLHOLDINGS/szl-governed-norm`` kernel card/contract.

It never rebuilds or replaces kernel binaries, model weights, dataset receipt
contents, visibility, or hardware. Existing kernel builds remain intact; only
reviewed README/contract files are updated after the corresponding Hub repo is
proved to be an existing first-class kernel repository.
"""
from __future__ import annotations

import argparse
import hashlib
import io
import json
import os
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import requests
from huggingface_hub import HfApi, hf_hub_download

ORG = "SZLHOLDINGS"
DATASET_ID = f"{ORG}/szl-lake"
EVIDENCE_DATASET = f"{ORG}/szl-evidence"
VIEWER_URL = (
    "https://datasets-server.huggingface.co/first-rows"
    "?dataset=SZLHOLDINGS%2Fszl-lake&config=receipts&split=train"
)
KERNEL_SPECS = {
    f"{ORG}/governed-inference-meter": {
        "source_root": "energy",
        "source_dir": "hf-kernels/governed-inference-meter",
    },
    f"{ORG}/szl-governed-norm": {
        "source_root": "lambda-gate",
        "source_dir": "hf-kernels/szl-governed-norm",
    },
}


@dataclass
class Action:
    target: str
    action: str
    status: str
    detail: str = ""


class Finalizer:
    def __init__(
        self,
        *,
        token: str,
        publish: bool,
        generation: str,
        lake_root: Path,
        energy_root: Path,
        lambda_root: Path,
    ) -> None:
        self.token = token
        self.publish = publish
        self.generation = generation
        self.roots = {
            "lake": lake_root,
            "energy": energy_root,
            "lambda-gate": lambda_root,
        }
        self.api = HfApi(token=token)
        self.actions: list[Action] = []
        self.results: dict[str, Any] = {}

    def record(self, target: str, action: str, status: str, detail: str = "") -> None:
        self.actions.append(Action(target, action, status, detail))
        print(f"[{status:>10}] {action}: {target}" + (f" — {detail}" if detail else ""))

    @staticmethod
    def digest(path: Path) -> str:
        return hashlib.sha256(path.read_bytes()).hexdigest()

    def authenticate(self) -> None:
        who = self.api.whoami()
        orgs = who.get("orgs") or []
        match = next(
            (
                item
                for item in orgs
                if str(item.get("name") or item.get("fullname") or "").upper()
                == ORG
            ),
            None,
        )
        if match is None:
            raise RuntimeError(f"authenticated identity is not a member of {ORG}")
        role = str(match.get("roleInOrg") or match.get("role") or "").lower()
        if role and role not in {"admin", "write", "contributor"}:
            raise RuntimeError(f"authenticated role is not write-capable: {role}")
        self.record(
            ORG,
            "authenticate",
            "validated",
            f"identity={who.get('name')}; role={role or 'unknown'}",
        )

    def _download_verified(
        self,
        repo_id: str,
        filename: str,
        repo_type: str,
        revision: str | None = None,
    ) -> bytes:
        local = hf_hub_download(
            repo_id=repo_id,
            filename=filename,
            repo_type=repo_type,
            revision=revision,
            token=self.token,
            force_download=True,
        )
        return Path(local).read_bytes()

    def finalize_dataset(self) -> None:
        root = self.roots["lake"]
        card = root / "huggingface" / "README.md"
        data = root / "data"
        if not card.is_file() or not data.is_dir():
            raise RuntimeError("szl-lake checkout is missing card or data directory")

        required = [
            data / "khipu" / "amaru_receipts.parquet",
            data / "khipu" / "sentra_receipts.parquet",
            data / "khipu" / "a11oy_receipts.parquet",
            data / "khipu" / "rosie_receipts.parquet",
            data / "khipu" / "killinchu_receipts.parquet",
            data / "khipu" / "EMPTY_CHAIN_MANIFEST.json",
        ]
        missing = [str(path.relative_to(root)) for path in required if not path.is_file()]
        if missing:
            raise RuntimeError(f"szl-lake viewer payload is incomplete: {missing}")

        before = self.api.dataset_info(DATASET_ID).sha
        self.record(
            DATASET_ID,
            "dataset-preflight",
            "validated",
            f"before={before}; card_sha256={self.digest(card)}",
        )

        if self.publish:
            self.api.upload_file(
                repo_id=DATASET_ID,
                repo_type="dataset",
                path_or_fileobj=str(card),
                path_in_repo="README.md",
                commit_message=(
                    "release(viewer): publish reviewed homogeneous receipts card "
                    f"{self.generation[:12]}"
                ),
                commit_description=(
                    "Source-controlled viewer contract from szl-holdings/szl-lake. "
                    "Only the five schema-compatible Khipu Parquet files are exposed "
                    "through the default receipts configuration."
                ),
            )
            self.api.upload_folder(
                repo_id=DATASET_ID,
                repo_type="dataset",
                folder_path=str(data),
                path_in_repo=".",
                commit_message=(
                    "release(data): mirror verified Lake payload "
                    f"{self.generation[:12]}"
                ),
                commit_description=(
                    "Verbatim additive mirror of data/**. Receipt bodies, signatures, "
                    "Parquet rows, and Khipu chains are not rewritten."
                ),
                ignore_patterns=["**/__pycache__/**", "*.pyc", "**/.pytest_cache/**"],
            )
            self.record(DATASET_ID, "dataset-publish", "updated")
        else:
            self.record(DATASET_ID, "dataset-publish", "dry-run")

        after = self.api.dataset_info(DATASET_ID).sha
        remote_card = self._download_verified(DATASET_ID, "README.md", "dataset", after)
        if remote_card != card.read_bytes():
            raise RuntimeError("published dataset card does not match reviewed source bytes")
        remote_files = set(self.api.list_repo_files(DATASET_ID, repo_type="dataset"))
        for expected in (
            "khipu/amaru_receipts.parquet",
            "khipu/sentra_receipts.parquet",
            "khipu/a11oy_receipts.parquet",
            "khipu/rosie_receipts.parquet",
            "khipu/killinchu_receipts.parquet",
            "khipu/EMPTY_CHAIN_MANIFEST.json",
        ):
            if expected not in remote_files:
                raise RuntimeError(f"published dataset is missing {expected}")

        response = requests.get(VIEWER_URL, timeout=90)
        if response.status_code != 200:
            raise RuntimeError(
                f"Dataset Viewer contract did not return HTTP 200: {response.status_code} "
                f"{response.text[:300]}"
            )
        payload = response.json()
        if not isinstance(payload, dict) or payload.get("error"):
            raise RuntimeError(f"Dataset Viewer returned an error payload: {payload}")
        self.record(
            DATASET_ID,
            "dataset-verify",
            "validated",
            f"after={after}; files={len(remote_files)}; viewer=HTTP-200",
        )
        self.results["dataset"] = {
            "repo_id": DATASET_ID,
            "before_sha": before,
            "after_sha": after,
            "card_sha256": self.digest(card),
            "viewer_http_status": response.status_code,
            "remote_file_count": len(remote_files),
        }

    def _kernel_selfcheck(self, repo_id: str, revision: str) -> Any:
        from kernels import get_kernel

        module = get_kernel(
            repo_id,
            revision=revision,
            trust_remote_code=True,
        )
        check = getattr(module, "selfcheck", None)
        if not callable(check):
            raise RuntimeError(f"{repo_id}@{revision} does not expose selfcheck()")
        result = check()
        if result is False:
            raise RuntimeError(f"{repo_id}@{revision} selfcheck returned false")
        if isinstance(result, dict) and result.get("ok") is False:
            raise RuntimeError(f"{repo_id}@{revision} selfcheck failed: {result}")
        return result

    def finalize_kernel(self, repo_id: str, spec: dict[str, str]) -> None:
        source_root = self.roots[spec["source_root"]]
        source_dir = source_root / spec["source_dir"]
        card = source_dir / "README.md"
        contract = source_dir / "contract.json"
        if not card.is_file() or not contract.is_file():
            raise RuntimeError(f"kernel source contract is incomplete: {source_dir}")
        contract_payload = json.loads(contract.read_text(encoding="utf-8"))
        if not isinstance(contract_payload, dict):
            raise RuntimeError(f"kernel contract is not an object: {contract}")

        before_info = self.api.kernel_info(repo_id)
        before = str(getattr(before_info, "sha", "") or "")
        if len(before) != 40:
            raise RuntimeError(f"kernel repository lacks immutable revision: {repo_id}")
        remote_files_before = set(self.api.list_repo_files(repo_id, repo_type="kernel"))
        if not any(path.startswith("build/") for path in remote_files_before):
            raise RuntimeError(f"first-class kernel repository lacks build variants: {repo_id}")
        self.record(
            repo_id,
            "kernel-preflight",
            "validated",
            f"before={before}; builds_present=true",
        )

        if self.publish:
            for source, destination in ((card, "README.md"), (contract, "contract.json")):
                self.api.upload_file(
                    repo_id=repo_id,
                    repo_type="kernel",
                    path_or_fileobj=str(source),
                    path_in_repo=destination,
                    commit_message=(
                        "release(card): publish reviewed kernel contract "
                        f"{self.generation[:12]}"
                    ),
                    commit_description=(
                        "Card/contract-only publication from the canonical GitHub owner. "
                        "Existing first-class kernel build variants are preserved."
                    ),
                )
            self.record(repo_id, "kernel-card-publish", "updated")
        else:
            self.record(repo_id, "kernel-card-publish", "dry-run")

        after_info = self.api.kernel_info(repo_id)
        after = str(getattr(after_info, "sha", "") or "")
        if len(after) != 40:
            raise RuntimeError(f"published kernel lacks immutable revision: {repo_id}")
        for source, filename in ((card, "README.md"), (contract, "contract.json")):
            observed = self._download_verified(repo_id, filename, "kernel", after)
            if observed != source.read_bytes():
                raise RuntimeError(
                    f"published kernel file differs from reviewed source: {repo_id}/{filename}"
                )
        remote_files_after = set(self.api.list_repo_files(repo_id, repo_type="kernel"))
        if not any(path.startswith("build/") for path in remote_files_after):
            raise RuntimeError(f"kernel publication removed build variants: {repo_id}")
        selfcheck = self._kernel_selfcheck(repo_id, after)
        self.record(
            repo_id,
            "kernel-verify",
            "validated",
            f"after={after}; selfcheck=passed; files={len(remote_files_after)}",
        )
        self.results.setdefault("kernels", {})[repo_id] = {
            "before_sha": before,
            "after_sha": after,
            "card_sha256": self.digest(card),
            "contract_sha256": self.digest(contract),
            "remote_file_count": len(remote_files_after),
            "selfcheck": selfcheck,
        }

    def report(self) -> dict[str, Any]:
        statuses = [action.status for action in self.actions]
        return {
            "schema": "szl.hf-release-finalization/v1",
            "organization": ORG,
            "generation": self.generation,
            "generated_at": datetime.now(timezone.utc).isoformat(),
            "publish": self.publish,
            "sources": {
                "szl_lake": os.environ.get("SZL_LAKE_SHA"),
                "szl_energy_attest": os.environ.get("SZL_ENERGY_ATTEST_SHA"),
                "szl_lambda_gate": os.environ.get("SZL_LAMBDA_GATE_SHA"),
            },
            "results": self.results,
            "actions": [asdict(action) for action in self.actions],
            "summary": {
                "ok": sum(
                    status in {"validated", "updated", "ok"} for status in statuses
                ),
                "warning": sum(status == "warning" for status in statuses),
                "error": sum(status == "error" for status in statuses),
                "dry_run": sum(status == "dry-run" for status in statuses),
            },
            "boundaries": [
                "Dataset receipt/data bytes are mirrored verbatim; no row or signature is synthesized.",
                "Only reviewed README.md and contract.json files are updated in existing first-class kernel repositories.",
                "Kernel build variants, visibility, and hardware are preserved.",
                "Kernel selfcheck is executed at the exact post-publication immutable revision.",
                "No model weights are trained, merged, relabeled, or promoted.",
            ],
        }

    def publish_evidence(self, report: dict[str, Any]) -> None:
        rendered = (json.dumps(report, indent=2, sort_keys=True, default=str) + "\n").encode()
        output = Path("reports/hf-release-finalization-latest.json")
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_bytes(rendered)
        self.record(str(output), "local-report", "updated")
        if not self.publish:
            return
        self.api.create_repo(
            repo_id=EVIDENCE_DATASET,
            repo_type="dataset",
            private=True,
            exist_ok=True,
        )
        timestamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
        for destination in (
            "release-finalization/latest.json",
            f"release-finalization/history/{timestamp}.json",
        ):
            self.api.upload_file(
                repo_id=EVIDENCE_DATASET,
                repo_type="dataset",
                path_or_fileobj=io.BytesIO(rendered),
                path_in_repo=destination,
                commit_message=f"release(evidence): record Hub finalization {timestamp}",
            )
        self.record(EVIDENCE_DATASET, "evidence-publish", "updated")

    def run(self) -> dict[str, Any]:
        self.authenticate()
        self.finalize_dataset()
        for repo_id, spec in KERNEL_SPECS.items():
            self.finalize_kernel(repo_id, spec)
        report = self.report()
        self.publish_evidence(report)
        report = self.report()
        Path("reports/hf-release-finalization-latest.json").write_text(
            json.dumps(report, indent=2, sort_keys=True, default=str) + "\n",
            encoding="utf-8",
        )
        return report


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--publish", action="store_true")
    parser.add_argument("--generation", required=True)
    parser.add_argument("--lake-root", default="lake")
    parser.add_argument("--energy-root", default="energy")
    parser.add_argument("--lambda-root", default="lambda-gate")
    args = parser.parse_args()

    token = (
        os.environ.get("HF_ORG_TOKEN")
        or os.environ.get("HF_ORG_TOKEN1")
        or os.environ.get("HF_TOKEN")
    )
    if not token:
        print("FATAL: no supported Hugging Face token is configured", file=os.sys.stderr)
        return 2

    try:
        report = Finalizer(
            token=token,
            publish=args.publish,
            generation=args.generation,
            lake_root=Path(args.lake_root),
            energy_root=Path(args.energy_root),
            lambda_root=Path(args.lambda_root),
        ).run()
    except Exception as exc:  # fail closed with an explicit local report when possible
        Path("reports").mkdir(exist_ok=True)
        failure = {
            "schema": "szl.hf-release-finalization/v1",
            "generation": args.generation,
            "publish": args.publish,
            "generated_at": datetime.now(timezone.utc).isoformat(),
            "fatal": f"{type(exc).__name__}: {exc}",
            "summary": {"ok": 0, "warning": 0, "error": 1, "dry_run": 0},
        }
        Path("reports/hf-release-finalization-latest.json").write_text(
            json.dumps(failure, indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )
        print(f"FATAL: {exc!r}", file=os.sys.stderr)
        return 2

    summary = report["summary"]
    print(json.dumps(summary, indent=2))
    return 1 if summary["error"] else 0


if __name__ == "__main__":
    raise SystemExit(main())
