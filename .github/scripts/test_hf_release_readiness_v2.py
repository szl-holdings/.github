#!/usr/bin/env python3
from __future__ import annotations

import importlib
import pathlib
import sys
import unittest

HERE = pathlib.Path(__file__).resolve().parent
if str(HERE) not in sys.path:
    sys.path.insert(0, str(HERE))

readiness = importlib.import_module("hf_release_readiness_v2")


class Response:
    def __init__(self, status: int, payload: object, text: str = "") -> None:
        self.status_code = status
        self._payload = payload
        self.text = text or str(payload)

    def json(self) -> object:
        return self._payload


class Session:
    def __init__(self, responses: list[object]) -> None:
        self.responses = iter(responses)
        self.calls = 0

    def get(self, *_args, **_kwargs):
        self.calls += 1
        value = next(self.responses)
        if isinstance(value, Exception):
            raise value
        return value


class KernelInfo:
    def __init__(self, sha: str = "a" * 40) -> None:
        self.sha = sha


class Api:
    def __init__(self, files: list[str] | None = None) -> None:
        self.files = files or [
            "README.md",
            "contract.json",
            "build/torch27-cxx11-cpu-x86_64-linux/__init__.py",
        ]
        self.info_calls: list[str] = []
        self.file_calls: list[tuple[str, str | None, str | None]] = []

    def kernel_info(self, repo_id: str) -> KernelInfo:
        self.info_calls.append(repo_id)
        return KernelInfo()

    def list_repo_files(
        self,
        repo_id: str,
        repo_type: str | None = None,
        revision: str | None = None,
    ) -> list[str]:
        self.file_calls.append((repo_id, repo_type, revision))
        return list(self.files)


class Module:
    def __init__(self, result: object) -> None:
        self.result = result

    def selfcheck(self) -> object:
        return self.result


class ReleaseReadinessV2Tests(unittest.TestCase):
    def test_viewer_retries_transient_then_requires_real_success(self) -> None:
        session = Session(
            [
                Response(500, {"error": "The server is busier than usual and not ready"}),
                Response(200, {"rows": [], "features": []}),
            ]
        )
        sleeps: list[float] = []
        response, payload, attempts = readiness.wait_for_viewer(
            session,
            attempts=3,
            retry_seconds=2,
            sleep=sleeps.append,
        )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(payload, {"rows": [], "features": []})
        self.assertEqual(attempts, 2)
        self.assertEqual(sleeps, [2])

    def test_viewer_fails_immediately_on_non_transient_response(self) -> None:
        session = Session([Response(404, {"error": "missing"})])
        with self.assertRaisesRegex(RuntimeError, "non-transiently"):
            readiness.wait_for_viewer(session, attempts=3, retry_seconds=0)
        self.assertEqual(session.calls, 1)

    def test_kernel_requires_exact_revision_builds_and_selfcheck(self) -> None:
        api = Api()
        observed = readiness.verify_kernel(
            api,
            "SZLHOLDINGS/example",
            loader=lambda repo_id, revision: Module(
                {"ok": True, "repo_id": repo_id, "revision": revision}
            ),
        )
        self.assertEqual(observed["revision"], "a" * 40)
        self.assertTrue(observed["build_variants_present"])
        self.assertTrue(observed["selfcheck"]["ok"])
        self.assertEqual(api.info_calls, ["SZLHOLDINGS/example"])
        self.assertEqual(
            api.file_calls,
            [("SZLHOLDINGS/example", "kernel", "a" * 40)],
        )

    def test_kernel_rejects_false_selfcheck(self) -> None:
        with self.assertRaisesRegex(RuntimeError, "selfcheck failed"):
            readiness.verify_kernel(
                Api(),
                "SZLHOLDINGS/example",
                loader=lambda _repo_id, _revision: Module(False),
            )

    def test_kernel_rejects_missing_build_variant(self) -> None:
        api = Api(files=["README.md", "contract.json"])
        with self.assertRaisesRegex(RuntimeError, "build variants are missing"):
            readiness.verify_kernel(
                api,
                "SZLHOLDINGS/example",
                loader=lambda _repo_id, _revision: Module(True),
            )

    def test_source_has_no_asset_mutation_path(self) -> None:
        source = (HERE / "hf_release_readiness_v2.py").read_text(encoding="utf-8")
        for forbidden in (
            "upload_file(",
            "upload_folder(",
            "create_repo(",
            "delete_repo(",
            "update_repo_settings(",
            "set_space_hardware(",
            "restart_space(",
        ):
            self.assertNotIn(forbidden, source)
        self.assertIn("torch27", source)
        self.assertIn("selfcheck()", source)


if __name__ == "__main__":
    unittest.main(verbosity=2)
