#!/usr/bin/env python3
"""Canonical Lake/Kernel finalizer using supported dataset APIs and Kernel Git.

This adapter permanently replaces the unsupported ``repo_type='kernel'`` path in
``hf_release_finalization``. Dataset behavior and bounded Viewer convergence stay
in the reviewed controller; first-class Kernel card/contract publication is
performed only by :class:`kernel_hub_git.KernelHubGitTransport`.
"""
from __future__ import annotations

import io
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Mapping

import hf_release_finalization as legacy
import hf_release_finalization_entrypoint as retry
from kernel_hub_git import KernelHubGitTransport, KernelPublication

REPORT_SCHEMA = "szl.hf-release-finalization/v2"


class KernelGitFinalizer(retry.RetryingFinalizer):
    """Use Git for Kernel repositories while retaining the dataset controller."""

    def __init__(
        self,
        *args: Any,
        kernel_transport: KernelHubGitTransport | None = None,
        **kwargs: Any,
    ) -> None:
        super().__init__(*args, **kwargs)
        self.kernel_transport = kernel_transport or KernelHubGitTransport(token=self.token)

    def _runtime(self) -> dict[str, str]:
        import numpy
        import torch

        if numpy.__version__ != "2.2.6":
            raise RuntimeError(f"unexpected NumPy runtime: {numpy.__version__}")
        if not torch.__version__.startswith("2.7.1"):
            raise RuntimeError(f"unexpected PyTorch runtime: {torch.__version__}")
        if torch.cuda.is_available():
            raise RuntimeError("release finalizer must use the CPU PyTorch runtime")
        return {"numpy": numpy.__version__, "torch": torch.__version__}

    def finalize_kernel(self, repo_id: str, spec: Mapping[str, str]) -> None:
        source_dir = self.roots[spec["source_root"]] / spec["source_dir"]
        for filename in ("README.md", "contract.json"):
            if not (source_dir / filename).is_file():
                raise RuntimeError(f"Kernel source contract is incomplete: {source_dir}")

        metadata_before = str(getattr(self.api.kernel_info(repo_id), "sha", "") or "")
        if len(metadata_before) != 40:
            raise RuntimeError(f"Kernel metadata lacks an immutable revision: {repo_id}")

        if self.publish:
            publication = self.kernel_transport.publish(
                repo_id=repo_id,
                source_dir=source_dir,
                metadata_revision=metadata_before,
                metadata_revision_after=lambda: str(
                    getattr(self.api.kernel_info(repo_id), "sha", "") or ""
                ),
                generation=self.generation,
            )
            action_status = "updated" if publication.changed else "validated"
        else:
            snapshot = self.kernel_transport.snapshot(repo_id)
            if snapshot.revision != metadata_before:
                raise RuntimeError(
                    f"Kernel metadata/Git mismatch: metadata={metadata_before}; "
                    f"git={snapshot.revision}; repo={repo_id}"
                )
            if not any(path.startswith("build/") for path in snapshot.files):
                raise RuntimeError(f"Kernel has no retained build variants: {repo_id}")
            publication = KernelPublication(
                repo_id=repo_id,
                before_revision=snapshot.revision,
                revision=snapshot.revision,
                changed=False,
                remote_file_count=len(snapshot.files),
                build_variants_preserved=True,
                card_contract_byte_parity=False,
                build_tree_sha256=snapshot.build_tree_sha256,
                remote_url=snapshot.remote_url,
            )
            action_status = "dry-run"

        self.record(
            repo_id,
            "kernel-card-publish",
            action_status,
            f"before={publication.before_revision}; after={publication.revision}; "
            f"changed={publication.changed}; transport=git",
        )
        selfcheck = self._kernel_selfcheck(repo_id, publication.revision)
        self.results.setdefault("kernels", {})[repo_id] = {
            "before_sha": publication.before_revision,
            "after_sha": publication.revision,
            "revision": publication.revision,
            "transport": "authenticated-kernel-hub-git",
            "changed": publication.changed,
            "remote_file_count": publication.remote_file_count,
            "build_variants_preserved": publication.build_variants_preserved,
            "card_contract_byte_parity": (
                publication.card_contract_byte_parity
                if self.publish
                else "NOT_EXECUTED_ON_PULL_REQUEST"
            ),
            "build_tree_sha256": publication.build_tree_sha256,
            "selfcheck": selfcheck,
        }
        self.record(
            repo_id,
            "kernel-verify",
            "validated",
            f"revision={publication.revision}; selfcheck=passed; "
            f"files={publication.remote_file_count}",
        )

    def report(self) -> dict[str, Any]:
        report = super().report()
        report["schema"] = REPORT_SCHEMA
        report["runtime"] = self._runtime()
        report["kernel_transport"] = "authenticated-kernel-hub-git"
        dataset = report.get("results", {}).get("dataset")
        if isinstance(dataset, dict):
            dataset["revision"] = dataset.get("after_sha") or dataset.get("revision")
        for item in report.get("results", {}).get("kernels", {}).values():
            if isinstance(item, dict):
                item["revision"] = item.get("after_sha") or item.get("revision")
        report["boundaries"] = [
            "Datasets use supported huggingface_hub dataset APIs only.",
            "First-class Kernels use credential-safe authenticated Git.",
            "Generic repository helpers are never called with repo_type=kernel.",
            "Only README.md and contract.json may change in Kernel repositories.",
            "The complete Kernel build tree and immutable revision binding are verified.",
            "No model, Space, visibility, hardware, training, weight, qualification, or promotion state is mutated.",
        ]
        return report

    def publish_evidence(self, report: dict[str, Any]) -> None:
        rendered = (json.dumps(report, indent=2, sort_keys=True, default=str) + "\n").encode()
        output = Path("reports/hf-release-finalization-latest.json")
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_bytes(rendered)
        self.record(str(output), "local-report", "updated")
        if not self.publish:
            return
        if not self.api.repo_exists(legacy.EVIDENCE_DATASET, repo_type="dataset"):
            raise RuntimeError(f"evidence dataset is missing: {legacy.EVIDENCE_DATASET}")
        timestamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
        for destination in (
            "release-finalization-v2/latest.json",
            f"release-finalization-v2/history/{timestamp}.json",
        ):
            self.api.upload_file(
                repo_id=legacy.EVIDENCE_DATASET,
                repo_type="dataset",
                path_or_fileobj=io.BytesIO(rendered),
                path_in_repo=destination,
                commit_message=f"release(evidence): record finalization v2 {timestamp}",
            )
        self.record(legacy.EVIDENCE_DATASET, "evidence-publish", "updated")


def main() -> int:
    # Retain the bounded Viewer retry adapter, but install the Git-backed Kernel
    # implementation as the sole Finalizer class used by the existing CLI.
    legacy.requests.get = retry.get_with_viewer_retry
    legacy.Finalizer = KernelGitFinalizer
    return legacy.main()


if __name__ == "__main__":
    raise SystemExit(main())
