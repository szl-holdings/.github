#!/usr/bin/env python3
"""Self-test for the org-wide receipt shape-conformance honesty guard.

``receipt_shape_check.py`` fails the run when a committed blob DECLARES a
well-known attestation format (via that format's own discriminator) but carries a
field that is PRESENT with the WRONG TYPE — structural corruption a real parser /
verifier would choke on, and which can never be an honest absence. It shares the
sibling energy guard's single lens: FABRICATION is the sin, honest ABSENCE is
not. An absent / null / empty field is the honest measured-or-UNAVAILABLE state
and is NEVER flagged (the org ships such honest stubs on purpose). These are
TYPE-conformance rules, not completeness rules.

  S1  in-toto Statement (``_type`` is exactly .../Statement/v1 or /v0.1):
        ``subject`` if present is a list; each entry is a dict; a subject
        ``digest`` if present is a dict of string values; ``predicateType`` if
        present is a string. Empty / absent = silent.
  S2  DSSE envelope (string ``payloadType`` + string ``payload``):
        a non-empty ``payload`` is base64-decodable; ``signatures`` if present is
        a list of dicts whose ``sig`` if present is a string. Empty / absent =
        silent.

``--local`` mode is fully network-free, so this test drives the REAL
``check_obj`` / ``scan_text`` / ``scan_local`` / ``main`` path against temp
checkouts.

The doctrine's hard edge is DO-NOT-PUNISH-HONESTY, so the must-PASS cases are as
load-bearing as the must-FAIL ones and are drawn from real org shapes:
  * an in-toto Statement with an intentionally EMPTY ``sha256`` digest and a
    "PENDING BUILD — nothing fabricated" note (the REAL uds-bundles stub, inlined
    verbatim below) — the guard must leave it alone;
  * an empty ``subject`` / missing ``predicateType`` (honest incomplete)  -> silent
  * an UNSIGNED DSSE envelope and a signature slot with no ``sig``          -> silent
  * an in-toto v0.1 statement carrying a 40-hex ``sha256`` value            -> silent
  * a JSON-Schema file, a JSON-LD ``@context``, a Khipu vector fixture      -> silent
The must-FAIL cases pin that a future weakening cannot turn the guard into a
no-op AND that present-but-wrong-type corruption is still caught.
"""
from __future__ import annotations

import base64
import contextlib
import importlib.util
import io
import json
import os
import sys
import tempfile
import unittest

_HERE = os.path.dirname(os.path.abspath(__file__))
_MODULE_PATH = os.path.join(_HERE, "receipt_shape_check.py")
_spec = importlib.util.spec_from_file_location("receipt_shape_check", _MODULE_PATH)
assert _spec and _spec.loader
rsc = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(rsc)

_NONEXISTENT_ALLOWLIST = os.path.join(tempfile.gettempdir(), "rsc_no_such_allowlist.json")

V1 = "https://in-toto.io/Statement/v1"
V01 = "https://in-toto.io/Statement/v0.1"

# The REAL szl-holdings/uds-bundles honest stub, verbatim. Its digest is
# intentionally "" (nothing fabricated) — the guard MUST leave it alone.
UDS_HONEST_STUB = r"""{
  "_comment": "PENDING FORGE BUILD. This is an HONEST STUB, not a signed attestation. The subject.digest is intentionally EMPTY — Forge fills the real sha256 after building ghcr.io/szl-holdings/khipu-sda-core:uds-v0.4.0 and running attest-build-provenance + cosign attest (keyless Fulcio/Rekor). NO digest or signature is fabricated. SLSA L1 honest; L2 build-attestation present where CI runs; L3 roadmap.",
  "_status": "STUB_PENDING_FORGE_BUILD_FA-001",
  "_type": "https://in-toto.io/Statement/v1",
  "subject": [
    {
      "name": "ghcr.io/szl-holdings/khipu-sda-core:uds-v0.4.0",
      "digest": {
        "sha256": ""
      }
    }
  ],
  "predicateType": "https://slsa.dev/provenance/v1",
  "predicate": {
    "buildDefinition": {
      "buildType": "https://github.com/slsa-framework/slsa-github-generator",
      "externalParameters": {
        "source": "https://github.com/szl-holdings/khipu-sda-core",
        "dockerfile": "Dockerfile",
        "baseImage": "python:3.12-slim"
      },
      "internalParameters": {
        "doctrine": "v11 LOCKED 749/14/163",
        "lambda": "Conjecture 1 (advisory, never a theorem)",
        "cleanroom": "INSPIRED BY True Anomaly Mosaic (capability only; no proprietary code)"
      }
    },
    "runDetails": {
      "builder": {
        "id": "https://github.com/szl-holdings/khipu-sda-core/.github/workflows/cosign.yml@refs/heads/main"
      },
      "metadata": {
        "_invocationId": "PENDING_FORGE_BUILD"
      }
    }
  }
}"""


def _run_local(root, allowlist=_NONEXISTENT_ALLOWLIST):
    """Run main() in --local mode over ``root``; return (exit_code, stdout)."""
    buf = io.StringIO()
    argv = ["receipt_shape_check.py", "--local", root, "--allowlist", allowlist]
    old = sys.argv
    sys.argv = argv
    try:
        with contextlib.redirect_stdout(buf):
            rc = rsc.main()
    finally:
        sys.argv = old
    return rc, buf.getvalue()


def _write(root, name, obj_or_text):
    path = os.path.join(root, name)
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as fh:
        fh.write(obj_or_text if isinstance(obj_or_text, str) else json.dumps(obj_or_text))
    return path


def _dsse(inner, sigs=None):
    env = {
        "payloadType": "application/vnd.in-toto+json",
        "payload": base64.b64encode(json.dumps(inner).encode()).decode(),
    }
    if sigs is not None:
        env["signatures"] = sigs
    return env


def _good_statement():
    return {
        "_type": V1,
        "subject": [{"name": "x", "digest": {"sha256": "abc123"}}],
        "predicateType": "https://slsa.dev/provenance/v1",
        "predicate": {"builder": {"id": "x"}},
    }


# --------------------------------------------------------------------------- #
# check_obj — the single source of truth for S1 / S2 (pin the edges directly).
# --------------------------------------------------------------------------- #
class TestInvariantEngine(unittest.TestCase):
    def _viol(self, obj):
        out = []
        rsc.check_obj(obj, "$", out)
        return out

    # --- S1 : PRESENT-but-WRONG-TYPE must FAIL --- #
    def test_s1_subject_not_a_list_fires(self):
        v = self._viol({"_type": V1, "subject": "nope", "predicateType": "p"})
        self.assertTrue(any(r == "S1" for (_, r, _) in v), v)

    def test_s1_subject_entry_not_a_dict_fires(self):
        v = self._viol({"_type": V1, "subject": ["x"], "predicateType": "p"})
        self.assertTrue(any(r == "S1" for (_, r, _) in v), v)

    def test_s1_digest_not_a_dict_fires(self):
        v = self._viol({"_type": V1, "subject": [{"digest": "deadbeef"}]})
        self.assertTrue(any(r == "S1" for (_, r, _) in v), v)

    def test_s1_digest_value_number_fires(self):
        v = self._viol({"_type": V1, "subject": [{"digest": {"sha256": 123}}]})
        self.assertTrue(any(r == "S1" for (_, r, _) in v), v)

    def test_s1_digest_value_bool_fires(self):
        # a hash is never a bool; True must not be waved through as "truthy".
        v = self._viol({"_type": V1, "subject": [{"digest": {"sha256": True}}]})
        self.assertTrue(any(r == "S1" for (_, r, _) in v), v)

    def test_s1_predicatetype_number_fires(self):
        v = self._viol({"_type": V1, "predicateType": 7})
        self.assertTrue(any(r == "S1" for (_, r, _) in v), v)

    # --- S1 : absent / null / empty must PASS (honest UNAVAILABLE) --- #
    def test_s1_uds_honest_stub_is_silent(self):
        # THE regression fixture: real org stub, digest intentionally "".
        self.assertEqual(self._viol(json.loads(UDS_HONEST_STUB)), [])

    def test_s1_empty_subject_is_silent(self):
        self.assertEqual(self._viol({"_type": V1, "subject": [], "predicateType": "p"}), [])

    def test_s1_missing_subject_and_predicatetype_is_silent(self):
        self.assertEqual(self._viol({"_type": V1}), [])

    def test_s1_empty_digest_string_is_silent(self):
        self.assertEqual(self._viol(
            {"_type": V1, "subject": [{"digest": {"sha256": ""}}], "predicateType": "p"}), [])

    def test_s1_null_digest_value_is_silent(self):
        self.assertEqual(self._viol(
            {"_type": V1, "subject": [{"digest": {"sha256": None}}]}), [])

    def test_s1_empty_digest_object_is_silent(self):
        self.assertEqual(self._viol({"_type": V1, "subject": [{"digest": {}}]}), [])

    def test_s1_subject_without_digest_is_silent(self):
        self.assertEqual(self._viol({"_type": V1, "subject": [{"name": "x"}]}), [])

    def test_s1_valid_v01_short_hex_is_silent(self):
        # Real org attestations carry a 40-hex value under a sha256 key: honest.
        self.assertEqual(self._viol({
            "_type": V01,
            "subject": [{"name": "n", "digest": {"sha256": "db6d4595da4260f56b768bfc5aae7c642d95fd90"}}],
            "predicateType": "https://slsa.dev/provenance/v0.2",
        }), [])

    def test_s1_valid_v1_is_silent(self):
        self.assertEqual(self._viol(_good_statement()), [])

    def test_s1_wrong_type_string_not_detected(self):
        self.assertEqual(self._viol({"_type": "https://example.com/Other/v1"}), [])

    def test_s1_type_as_schema_object_not_detected(self):
        # A JSON-Schema that DESCRIBES the _type (a dict, not the string) is not
        # an in-toto Statement -> no rule.
        self.assertEqual(self._viol({"_type": {"const": V1}, "properties": {}}), [])

    # --- S2 : PRESENT-but-WRONG-TYPE must FAIL --- #
    def test_s2_nondecodable_payload_fires(self):
        v = self._viol({"payloadType": "application/vnd.dsse+json", "payload": "!!!"})
        self.assertTrue(any(r == "S2" for (_, r, _) in v), v)

    def test_s2_signatures_not_a_list_fires(self):
        env = _dsse(_good_statement())
        env["signatures"] = {"sig": "x"}
        v = self._viol(env)
        self.assertTrue(any(r == "S2" for (_, r, _) in v), v)

    def test_s2_signature_entry_not_a_dict_fires(self):
        v = self._viol(_dsse(_good_statement(), sigs=["justastring"]))
        self.assertTrue(any(r == "S2" for (_, r, _) in v), v)

    def test_s2_sig_wrong_type_fires(self):
        v = self._viol(_dsse(_good_statement(), sigs=[{"sig": 123}]))
        self.assertTrue(any(r == "S2" for (_, r, _) in v), v)

    # --- S2 : absent / null / empty must PASS (honest UNAVAILABLE) --- #
    def test_s2_unsigned_envelope_is_silent(self):
        self.assertEqual(self._viol(_dsse(_good_statement())), [])

    def test_s2_empty_signatures_list_is_silent(self):
        self.assertEqual(self._viol(_dsse(_good_statement(), sigs=[])), [])

    def test_s2_signature_slot_without_sig_is_silent(self):
        # a signature slot with no `sig` (pending-honest) -> silent.
        self.assertEqual(self._viol(_dsse(_good_statement(), sigs=[{"keyid": "k"}])), [])

    def test_s2_empty_sig_string_is_silent(self):
        self.assertEqual(self._viol(_dsse(_good_statement(), sigs=[{"sig": ""}])), [])

    def test_s2_empty_payload_is_silent(self):
        self.assertEqual(self._viol({"payloadType": "app/x", "payload": ""}), [])

    def test_s2_valid_signed_envelope_is_silent(self):
        self.assertEqual(self._viol(_dsse(_good_statement(), sigs=[{"sig": "MEUCIQ..."}])), [])

    def test_s2_bespoke_singular_signature_is_silent(self):
        env = _dsse(_good_statement())
        env["signature"] = "MEUCIQ..."
        env["signed"] = True
        self.assertEqual(self._viol(env), [])

    def test_s2_payloadtype_without_string_payload_not_detected(self):
        # Khipu vectors: payloadType present, payload absent/non-string -> not a
        # DSSE envelope -> no rule.
        self.assertEqual(self._viol({"payloadType": "app/x", "cases": []}), [])
        self.assertEqual(self._viol({"payloadType": "app/x", "payload": {"a": 1}}), [])

    # --- recursion: a wrong-typed in-toto Statement wrapped in a DSSE payload --- #
    def test_dsse_wrapped_wrongtype_statement_fires(self):
        broken = {"_type": V1, "subject": "nope", "predicateType": "p"}
        v = self._viol(_dsse(broken))
        self.assertTrue(any(r == "S1" for (_, r, _) in v), v)
        self.assertTrue(any("payload~b64" in loc for (loc, _, _) in v), v)

    def test_dsse_wrapped_honest_stub_is_silent(self):
        # an honest (empty-field) Statement wrapped in a DSSE envelope stays silent.
        v = self._viol(_dsse({"_type": V1, "subject": [], "predicateType": "p"}))
        self.assertEqual(v, [])


# --------------------------------------------------------------------------- #
# main() --local — end-to-end exit-code contract.
# --------------------------------------------------------------------------- #
class TestLocalMode(unittest.TestCase):
    def test_clean_checkout_exits_zero(self):
        with tempfile.TemporaryDirectory() as d:
            _write(d, "uds_stub.json", UDS_HONEST_STUB)
            _write(d, "stmt_v1.json", _good_statement())
            _write(d, "stmt_v01.json", {
                "_type": V01,
                "subject": [{"name": "n", "digest": {"sha256": "db6d4595da4260f56b768bfc5aae7c642d95fd90"}}],
                "predicateType": "https://slsa.dev/provenance/v0.2",
            })
            _write(d, "unsigned_envelope.json", _dsse(_good_statement()))
            _write(d, "schema.json", {"$schema": "x", "type": "object", "properties": {}})
            _write(d, "context.json", {"@context": {"id": "@id"}})
            _write(d, "vectors.json", {"payloadType": "app/x", "cases": [], "n": 5})
            rc, _ = _run_local(d)
            self.assertEqual(rc, 0)

    def test_wrongtype_digest_exits_one(self):
        with tempfile.TemporaryDirectory() as d:
            _write(d, "bad.json", {"_type": V1, "subject": [{"digest": {"sha256": 123}}]})
            rc, out = _run_local(d)
            self.assertEqual(rc, 1)
            self.assertIn("S1", out)

    def test_wrongtype_signature_exits_one(self):
        with tempfile.TemporaryDirectory() as d:
            _write(d, "bad.json", _dsse(_good_statement(), sigs=[{"sig": 123}]))
            rc, out = _run_local(d)
            self.assertEqual(rc, 1)
            self.assertIn("S2", out)

    def test_jsonl_line_level_exits_one(self):
        with tempfile.TemporaryDirectory() as d:
            good = json.dumps(_good_statement())
            bad = json.dumps({"_type": V1, "subject": "nope"})
            _write(d, "ledger.jsonl", good + "\n" + bad + "\n")
            rc, out = _run_local(d)
            self.assertEqual(rc, 1)
            self.assertIn("L2", out)

    def test_allowlisted_negative_fixture_exits_zero(self):
        with tempfile.TemporaryDirectory() as d:
            _write(d, "fixtures/wrongtype_demo.json",
                   {"_type": V1, "subject": [{"digest": {"sha256": 123}}]})
            allow = os.path.join(d, "allow.json")
            with open(allow, "w", encoding="utf-8") as fh:
                json.dump({"ignore_paths": ["fixtures/wrongtype_demo.json"]}, fh)
            rc, _ = _run_local(d, allowlist=allow)
            self.assertEqual(rc, 0)


if __name__ == "__main__":
    unittest.main(verbosity=2)
