import json
import types
import unittest
from unittest import mock

import hf_space_visibility as visibility


class FakeResponse:
    def __init__(
        self,
        payload,
        status=200,
        url="https://huggingface.co/api/spaces/SZLHOLDINGS/README",
    ):
        self.payload = json.dumps(payload).encode("utf-8")
        self.status = status
        self.url = url

    def __enter__(self):
        return self

    def __exit__(self, *args):
        return False

    def read(self, size=-1):
        return self.payload[:size]

    def geturl(self):
        return self.url

    def getcode(self):
        return self.status


class FakeApi:
    def __init__(self, *, token, before="private", after="public"):
        self.token = token
        self.before = before
        self.after = after
        self.updated = False
        self.calls = []

    def repo_info(self, *, repo_id, repo_type):
        current = self.after if self.updated else self.before
        return types.SimpleNamespace(
            visibility=current,
            private=current == "private",
        )

    def update_repo_settings(self, **kwargs):
        self.calls.append(kwargs)
        self.updated = True


class SpaceVisibilityTests(unittest.TestCase):
    def test_sets_public_and_proves_unauthenticated_readability(self):
        api = FakeApi(token="redacted")

        report = visibility.ensure_public_space(
            "SZLHOLDINGS/README",
            "redacted",
            wait_seconds=3,
            api_factory=lambda **_: api,
            opener=lambda *_args, **_kwargs: FakeResponse(
                {
                    "id": "SZLHOLDINGS/README",
                    "visibility": "public",
                    "private": False,
                }
            ),
            sleeper=lambda _seconds: None,
        )

        self.assertTrue(report.unauthenticated_readable)
        self.assertTrue(report.changed)
        self.assertEqual(report.unauthenticated_visibility, "public")
        self.assertEqual(
            api.calls,
            [
                {
                    "repo_id": "SZLHOLDINGS/README",
                    "repo_type": "space",
                    "visibility": "public",
                }
            ],
        )

    def test_private_false_is_accepted_for_older_public_metadata(self):
        api = FakeApi(token="redacted", before="public", after="public")
        report = visibility.ensure_public_space(
            "SZLHOLDINGS/README",
            "redacted",
            wait_seconds=2,
            check_only=True,
            api_factory=lambda **_: api,
            opener=lambda *_args, **_kwargs: FakeResponse(
                {"id": "SZLHOLDINGS/README", "private": False}
            ),
            sleeper=lambda _seconds: None,
        )
        self.assertEqual(report.unauthenticated_visibility, "public")
        self.assertFalse(report.changed)
        self.assertEqual(api.calls, [])

    def test_protected_metadata_fails_closed(self):
        api = FakeApi(token="redacted", before="protected", after="protected")
        with self.assertRaisesRegex(
            visibility.VisibilityContractError,
            "does not report a public Space",
        ):
            visibility.ensure_public_space(
                "SZLHOLDINGS/README",
                "redacted",
                wait_seconds=2,
                check_only=True,
                api_factory=lambda **_: api,
                opener=lambda *_args, **_kwargs: FakeResponse(
                    {"id": "SZLHOLDINGS/README", "visibility": "protected"}
                ),
                sleeper=lambda _seconds: None,
            )

    def test_wrong_public_repo_id_never_passes(self):
        api = FakeApi(token="redacted", before="public", after="public")
        clock = iter([0.0, 0.0, 1.1])
        with mock.patch.object(
            visibility.time,
            "monotonic",
            side_effect=lambda: next(clock),
        ):
            with self.assertRaisesRegex(
                visibility.VisibilityContractError,
                "did not become publicly readable",
            ):
                visibility.ensure_public_space(
                    "SZLHOLDINGS/README",
                    "redacted",
                    wait_seconds=1,
                    check_only=True,
                    api_factory=lambda **_: api,
                    opener=lambda *_args, **_kwargs: FakeResponse(
                        {"id": "OTHER/README", "visibility": "public"}
                    ),
                    sleeper=lambda _seconds: None,
                )

    def test_untrusted_redirect_is_rejected(self):
        with self.assertRaisesRegex(
            visibility.VisibilityContractError,
            "left the Hugging Face origin",
        ):
            visibility.fetch_public_metadata(
                "SZLHOLDINGS/README",
                opener=lambda *_args, **_kwargs: FakeResponse(
                    {"id": "SZLHOLDINGS/README", "visibility": "public"},
                    url="https://evil.example/api/spaces/SZLHOLDINGS/README",
                ),
            )

    def test_missing_token_fails_before_network(self):
        with self.assertRaisesRegex(visibility.VisibilityContractError, "HF_TOKEN"):
            visibility.ensure_public_space("SZLHOLDINGS/README", "")

    def test_main_never_prints_token(self):
        report = visibility.VisibilityReport(
            schema="szl.hf-space-visibility/v1",
            repo_id="SZLHOLDINGS/README",
            requested_visibility="public",
            authenticated_visibility="public",
            unauthenticated_status=200,
            unauthenticated_visibility="public",
            unauthenticated_readable=True,
            changed=True,
        )
        with mock.patch.dict(
            "os.environ",
            {"HF_TOKEN": "super-secret-token"},
            clear=False,
        ):
            with mock.patch.object(
                visibility,
                "ensure_public_space",
                return_value=report,
            ):
                with mock.patch("builtins.print") as printer:
                    rc = visibility.main(["--repo-id", "SZLHOLDINGS/README"])
        self.assertEqual(rc, 0)
        output = " ".join(
            str(arg)
            for call in printer.call_args_list
            for arg in call.args
        )
        self.assertNotIn("super-secret-token", output)


if __name__ == "__main__":
    unittest.main()
