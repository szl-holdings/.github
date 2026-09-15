#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
"""Offline regression tests of the source-owned publisher's read transport.

All destinations are inert strings. No real credentials, sockets, Hub writes,
queue actions, or independently authenticated provenance are used.
"""
from __future__ import annotations

import importlib.util
import io
from email.message import Message
from pathlib import Path
import unittest
import unittest.mock as mock
import urllib.error
import urllib.request

HERE = Path(__file__).resolve().parent
SPEC = importlib.util.spec_from_file_location(
    "hf_http_boundary_subject", HERE / "hf_deploy_from_dockerfile.py"
)
if SPEC is None or SPEC.loader is None:
    raise RuntimeError("source-owned publisher missing")
subject = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(subject)
HUB = "https://huggingface.co/api/spaces/SZLHOLDINGS/fixture"
TOKEN = "fixture-control-token-not-a-credential"
CDN = "https://cas-bridge.xethub.hf.co/fixture?signature=inert"


class Reply(io.BytesIO):
    def __init__(self, body=b"ok", status=200, headers=None):
        super().__init__(body)
        self.status = status
        self.headers = headers or {}
        self.read_sizes = []

    def read(self, size=-1):
        self.read_sizes.append(size)
        return super().read(size)


class HttpBoundaryTests(unittest.TestCase):
    def setUp(self):
        self.addCleanup(mock.patch.stopall)
        mock.patch("socket.create_connection", side_effect=AssertionError("network forbidden")).start()
        self.sleep = mock.patch.object(subject.time, "sleep").start()
        self.responses = []
        self.requests = []
        self.handlers = []
        self.redirect_to = None
        self.builder = mock.patch.object(
            subject.urllib.request, "build_opener", side_effect=self.build_opener
        ).start()
        # Small body limits exercise byte-boundary logic without resource abuse.
        mock.patch.object(subject, "HTTP_MAX_RESPONSE_BYTES", 64, create=True).start()
        mock.patch.object(subject, "HTTP_MAX_ERROR_BYTES", 16, create=True).start()

    def build_opener(self, *handlers):
        self.handlers = list(handlers)
        return mock.Mock(open=self.open_request)

    def open_request(self, request, timeout):
        self.requests.append(request)
        self.assertEqual(timeout, 45)
        if self.redirect_to:
            handler = next((h for h in self.handlers if isinstance(
                h, urllib.request.HTTPRedirectHandler
            )), urllib.request.HTTPRedirectHandler())
            target, self.redirect_to = self.redirect_to, None
            redirected = handler.redirect_request(
                request, None, 302, "inert", {}, target
            )
            if redirected is None:
                raise urllib.error.HTTPError(request.full_url, 302, "inert", {}, io.BytesIO(b"moved"))
            self.requests.append(redirected)
        response = self.responses.pop(0) if self.responses else Reply()
        if isinstance(response, Exception):
            raise response
        return response

    def error(self, code, retry_after=None, body=b"unavailable"):
        headers = {} if retry_after is None else {"Retry-After": retry_after}
        return urllib.error.HTTPError(HUB, code, "inert", headers, io.BytesIO(body))

    def test_get_method_only_and_existing_socket_timeout(self):
        self.assertEqual(subject._http(HUB), (200, b"ok"))
        self.assertEqual(self.requests[0].get_method(), "GET")

    def test_hub_control_auth_is_retained_on_initial_request(self):
        subject._http(HUB, headers={"Authorization": "Bearer " + TOKEN})
        self.assertEqual(self.requests[0].get_header("Authorization"), "Bearer " + TOKEN)

    def test_explicit_empty_proxy_handler_prevents_environment_proxy_use(self):
        subject._http(HUB)
        proxies = [h for h in self.handlers if isinstance(h, urllib.request.ProxyHandler)]
        self.assertEqual(len(proxies), 1)
        self.assertEqual(proxies[0].proxies, {})

    def test_cdn_redirect_cannot_forward_hub_bearer(self):
        self.redirect_to = CDN
        subject._http(HUB, headers={"Authorization": "Bearer " + TOKEN})
        self.assertEqual(len(self.requests), 2)
        self.assertIsNone(self.requests[1].get_header("Authorization"))

    def test_same_hub_origin_redirect_preserves_management_auth(self):
        self.redirect_to = "/api/resolve-cache/fixture"
        subject._http(HUB, headers={"Authorization": "Bearer " + TOKEN})
        self.assertEqual(self.requests[-1].get_header("Authorization"), "Bearer " + TOKEN)

    def test_cdn_redirect_strips_cookie_and_proxy_auth_from_request_object(self):
        # Exercise the exact handler even for a contaminated Request object;
        # normal _http header validation rejects these headers earlier.
        subject._http(HUB)
        handler = next((h for h in self.handlers if isinstance(
            h, urllib.request.HTTPRedirectHandler
        )), urllib.request.HTTPRedirectHandler())
        req = urllib.request.Request(HUB, headers={
            "Authorization": "Bearer " + TOKEN,
            "Cookie": "inert-session", "Proxy-Authorization": "inert-proxy",
        })
        target = handler.redirect_request(req, None, 302, "inert", {}, CDN)
        self.assertIsNone(target.get_header("Authorization"))
        self.assertIsNone(target.get_header("Cookie"))
        self.assertIsNone(target.get_header("Proxy-authorization"))

    def test_redirect_response_is_closed_without_unbounded_body_drain(self):
        subject._http(HUB)
        handler = next((h for h in self.handlers if isinstance(
            h, urllib.request.HTTPRedirectHandler
        )), urllib.request.HTTPRedirectHandler())
        handler.parent = mock.Mock(open=mock.Mock(return_value="redirect-result"))
        for code in (301, 302, 303, 307, 308):
            with self.subTest(code=code):
                old_response = Reply(b"body must not be drained")
                req = urllib.request.Request(HUB, headers={"Authorization": "Bearer " + TOKEN})
                req.timeout = 45
                redirect_headers = Message()
                redirect_headers["Location"] = CDN
                result = getattr(handler, "http_error_" + str(code))(
                    req, old_response, code, "inert", redirect_headers
                )
                self.assertEqual(result, "redirect-result")
                self.assertEqual(old_response.read_sizes, [])
                self.assertTrue(old_response.closed)
                forwarded = handler.parent.open.call_args.args[0]
                self.assertIsNone(forwarded.get_header("Authorization"))

    def test_missing_redirect_location_is_a_closed_failure(self):
        subject._http(HUB)
        handler = next((h for h in self.handlers if isinstance(
            h, urllib.request.HTTPRedirectHandler
        )), urllib.request.HTTPRedirectHandler())
        reply = Reply()
        with self.assertRaises(RuntimeError):
            handler.http_error_302(urllib.request.Request(HUB), reply, 302, "inert", {})
        self.assertTrue(reply.closed)

    def test_https_downgrade_redirect_fails(self):
        self.redirect_to = "http://huggingface.co/inert"
        with self.assertRaises(RuntimeError):
            subject._http(HUB, headers={"Authorization": "Bearer " + TOKEN})

    def test_external_redirect_fails_before_destination_request(self):
        self.redirect_to = "https://outside.invalid/inert"
        with self.assertRaises(RuntimeError):
            subject._http(HUB)
        self.assertEqual(len(self.requests), 1)

    def test_lookalike_hub_redirect_is_rejected(self):
        self.redirect_to = "https://huggingface.co.outside.invalid/inert"
        with self.assertRaises(RuntimeError):
            subject._http(HUB)

    def test_hub_redirect_cannot_enter_an_application(self):
        self.redirect_to = "https://szlholdings-finance.hf.space/"
        with self.assertRaises(RuntimeError):
            subject._http(HUB)

    def test_application_redirects_remain_disabled(self):
        self.redirect_to = CDN
        self.assertEqual(subject._http(
            "https://szlholdings-fixture.hf.space/", follow_redirects=False
        ), (302, b"moved"))
        self.assertEqual(len(self.requests), 1)

    def test_http_initial_url_is_rejected_before_open(self):
        with self.assertRaises(RuntimeError):
            subject._http("http://huggingface.co/inert")
        self.builder.assert_not_called()

    def test_external_initial_url_is_rejected(self):
        with self.assertRaises(RuntimeError):
            subject._http("https://outside.invalid/inert")
        self.builder.assert_not_called()

    def test_wrong_port_is_rejected(self):
        with self.assertRaises(RuntimeError):
            subject._http("https://huggingface.co:8443/inert")
        self.builder.assert_not_called()

    def test_url_userinfo_is_rejected(self):
        with self.assertRaises(RuntimeError):
            subject._http("https://user@huggingface.co/inert")
        self.builder.assert_not_called()

    def test_url_controls_are_rejected(self):
        with self.assertRaises(RuntimeError):
            subject._http("https://huggingface.co/\ninert")
        self.builder.assert_not_called()

    def test_hub_bearer_on_app_origin_is_rejected(self):
        with self.assertRaises(RuntimeError):
            subject._http("https://szlholdings-fixture.hf.space/",
                          headers={"Authorization": "Bearer " + TOKEN})
        self.builder.assert_not_called()

    def test_cookie_request_header_is_rejected(self):
        with self.assertRaises(RuntimeError):
            subject._http(HUB, headers={"Cookie": "inert"})
        self.builder.assert_not_called()

    def test_host_override_is_rejected(self):
        with self.assertRaises(RuntimeError):
            subject._http(HUB, headers={"Host": "outside.invalid"})
        self.builder.assert_not_called()

    def test_duplicate_casefolded_header_is_rejected(self):
        with self.assertRaises(RuntimeError):
            subject._http(HUB, headers={"Authorization": "inert", "authorization": "inert"})
        self.builder.assert_not_called()

    def test_header_control_characters_are_rejected_before_open(self):
        with self.assertRaises(RuntimeError):
            subject._http(HUB, headers={"X-Inert": "x\r\ninert"})
        self.builder.assert_not_called()

    def test_colon_in_request_header_name_is_rejected_before_open(self):
        with self.assertRaises(RuntimeError):
            subject._http(HUB, headers={"Authorization:": "inert"})
        self.builder.assert_not_called()

    def test_declared_oversize_body_fails_without_reading(self):
        reply = Reply(b"x" * 65, headers={"Content-Length": "65"})
        self.responses = [reply]
        with self.assertRaises(RuntimeError):
            subject._http(HUB)
        self.assertEqual(reply.read_sizes, [])
        self.assertTrue(reply.closed)

    def test_undeclared_oversize_body_fails_instead_of_truncating(self):
        reply = Reply(b"x" * 65)
        self.responses = [reply]
        with self.assertRaises(RuntimeError):
            subject._http(HUB)
        self.assertTrue(all(0 < n <= 65 for n in reply.read_sizes))
        self.assertTrue(reply.closed)

    def test_exact_limit_body_is_preserved(self):
        raw = b"x" * 64
        self.responses = [Reply(raw, headers={"Content-Length": "64"})]
        self.assertEqual(subject._http(HUB), (200, raw))

    def test_no_unbounded_response_read(self):
        reply = Reply(b"abc")
        self.responses = [reply]
        self.assertEqual(subject._http(HUB), (200, b"abc"))
        self.assertTrue(all(n > 0 for n in reply.read_sizes))

    def test_truncated_declared_body_is_rejected(self):
        self.responses = [Reply(b"abc", headers={"Content-Length": "4"})]
        with self.assertRaises(RuntimeError):
            subject._http(HUB)

    def test_negative_content_length_is_rejected(self):
        self.responses = [Reply(b"abc", headers={"Content-Length": "-1"})]
        with self.assertRaises(RuntimeError):
            subject._http(HUB)

    def test_multiple_content_lengths_are_rejected(self):
        headers = Message()
        headers.add_header("Content-Length", "3")
        headers.add_header("Content-Length", "9")
        self.responses = [Reply(b"abc", headers=headers)]
        with self.assertRaises(RuntimeError):
            subject._http(HUB)

    def test_oversize_nonretryable_error_body_is_rejected_and_closed(self):
        error = self.error(403, body=b"x" * 17)
        stream = error.fp
        self.responses = [error]
        with self.assertRaises(RuntimeError):
            subject._http(HUB)
        self.assertTrue(stream.closed)

    def test_ordinary_nonretryable_error_preserves_status(self):
        error = self.error(403, body=b"denied")
        stream = error.fp
        self.responses = [error]
        self.assertEqual(subject._http(HUB), (403, b"denied"))
        self.assertEqual(len(self.requests), 1)
        self.sleep.assert_not_called()
        self.assertTrue(stream.closed)

    def test_429_is_retried_before_generic_4xx_handling(self):
        self.responses = [self.error(429, "1"), Reply()]
        self.assertEqual(subject._http(HUB, retries=2), (200, b"ok"))
        self.assertEqual(len(self.requests), 2)
        self.sleep.assert_called_once_with(1.0)

    def test_one_attempt_503_does_not_sleep(self):
        self.responses = [self.error(503, "3600")]
        with self.assertRaises(RuntimeError):
            subject._http(HUB, retries=1)
        self.sleep.assert_not_called()

    def test_one_attempt_429_does_not_sleep(self):
        self.responses = [self.error(429, "3600")]
        with self.assertRaises(RuntimeError):
            subject._http(HUB, retries=1)
        self.sleep.assert_not_called()

    def test_retry_after_is_capped(self):
        self.responses = [self.error(503, "3600"), Reply()]
        self.assertEqual(subject._http(HUB, retries=2), (200, b"ok"))
        self.sleep.assert_called_once_with(30.0)

    def test_nonfinite_retry_after_uses_bounded_fallback(self):
        for value in ("nan", "inf", "-inf", "1e9999", "-1", "invalid"):
            with self.subTest(value=value):
                self.sleep.reset_mock()
                self.responses = [self.error(503, value), Reply()]
                self.assertEqual(subject._http(HUB, retries=2), (200, b"ok"))
                self.sleep.assert_called_once_with(2.0)

    def test_zero_retry_after_is_respected(self):
        self.responses = [self.error(503, "0"), Reply()]
        self.assertEqual(subject._http(HUB, retries=2), (200, b"ok"))
        self.sleep.assert_called_once_with(0.0)

    def test_exhaustion_has_exact_attempt_count_and_no_final_sleep(self):
        self.responses = [self.error(503) for _ in range(3)]
        with self.assertRaises(RuntimeError):
            subject._http(HUB, retries=3)
        self.assertEqual(len(self.requests), 3)
        self.assertEqual(self.sleep.call_count, 2)

    def test_retryable_errors_are_closed_without_reading_their_bodies(self):
        error = self.error(503)
        stream = error.fp
        self.responses = [error, Reply()]
        self.assertEqual(subject._http(HUB, retries=2), (200, b"ok"))
        self.assertTrue(stream.closed)

    def test_transport_error_and_signed_query_are_not_reflected(self):
        self.responses = [urllib.error.URLError("PRIVATE_PROVIDER_ERROR_" + TOKEN)]
        with self.assertRaises(RuntimeError) as raised:
            subject._http(HUB + "?token=PRIVATE_SIGNED_QUERY", retries=1)
        message = str(raised.exception)
        self.assertNotIn(TOKEN, message)
        self.assertNotIn("PRIVATE", message)
        self.assertNotIn("?", message)
        self.sleep.assert_not_called()

    def test_boolean_retry_count_is_rejected(self):
        with self.assertRaises(RuntimeError):
            subject._http(HUB, retries=True)
        self.builder.assert_not_called()

    def test_zero_retry_count_is_rejected_before_open(self):
        with self.assertRaises(RuntimeError):
            subject._http(HUB, retries=0)
        self.builder.assert_not_called()

    def test_excessive_retry_count_is_rejected(self):
        with self.assertRaises(RuntimeError):
            subject._http(HUB, retries=11)
        self.builder.assert_not_called()

    def test_non_boolean_redirect_setting_is_rejected(self):
        with self.assertRaises(RuntimeError):
            subject._http(HUB, follow_redirects="false")
        self.builder.assert_not_called()


if __name__ == "__main__":
    unittest.main()
