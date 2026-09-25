"""Offline tests for szl_frontier_compass.py (no network). Run: python -m pytest -q test_szl_frontier_compass.py"""
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import szl_frontier_compass as C  # noqa: E402

CANON = {"numbers": {"declarations": 749, "axioms_raw": 15, "axioms_unique": 14, "sorries_raw": 163,
                     "sorries_noncomment": 146, "sorries_putnam": 51, "sorries_baseline": 112, "locked_formula_count": 8},
         "sha": "c7c0ba17"}
HEAD = {"state": "MEASURED", "sha": "f" * 40, "declarations": 2087, "axioms_unique": 30, "axioms_raw": 31, "sorries_raw": 70,
        "sorries_noncomment": 66, "sorries_baseline": 60, "sorries_putnam": 10}
TRUTH = {"lean": {"canonical": CANON, "head": HEAD}, "counts": {"repos": 69, "repos_total": 94, "models": 49, "spaces": 22, "datasets": 35}}


def classify(surfaces):
    claims = C.extract_claims(surfaces)
    cons = C.classify_claims(claims, TRUTH)
    return claims, cons


def cls_of(claims, key, value):
    return {c["cls"] for c in claims if c["key"] == key and c["value"] == value}


def test_lean_count_matches_canonical_method():
    files = [("Lutar/A.lean", "theorem a : True := trivial\nprivate noncomputable def b := 1\naxiom foo : Nat\naxiom foo : Nat\n"
                              "-- sorry in a comment\nexample : 1 = 1 := by sorry\n  theorem indented : True := trivial\n"),
             ("Lutar/Putnam/P.lean", "lemma p : True := sorry\nstructure S where\n")]
    n = C.lean_count(files)
    assert n["declarations"] == 4  # theorem, def, lemma, structure (indented theorem not counted, as canonical)
    assert n["axioms_raw"] == 2 and n["axioms_unique"] == 1
    assert n["sorries_raw"] == 3 and n["sorries_noncomment"] == 2
    assert n["sorries_putnam"] == 1 and n["sorries_baseline"] == 2


def test_locked_figures_are_canonical_not_findings():
    claims, _ = classify({"https://x/": "The corpus has 749 declarations, 14 axioms and 163 sorries (749/14/163 locked)."})
    assert cls_of(claims, "lean_declarations", "749") == {"CANONICAL"}
    assert cls_of(claims, "lean_axioms", "14") == {"CANONICAL"}
    assert cls_of(claims, "lean_sorries", "163") == {"CANONICAL"}
    assert cls_of(claims, "doctrine_triple", "749/14/163") == {"CANONICAL"}


def test_zero_and_standard_axioms_are_scoped():
    claims, _ = classify({"https://x/trust": "Locked formulas: 0 sorries, 0 axioms.",
                          "https://x/b": "depends only on 3 axioms: propext, Quot.sound and Classical.choice",
                          "https://x/c": "only the 3 standard axioms"})
    assert cls_of(claims, "lean_sorries", "0") == {"SCOPED"}
    assert cls_of(claims, "lean_axioms", "3") == {"SCOPED"}
    assert not [c for c in claims if c.get("cls") == "UNEXPLAINED"]


def test_unexplained_lean_value_is_flagged_and_current_is_not():
    claims, cons = classify({"github:szl-holdings/lutar-lean#README": "Lutar has 1323 declarations and 23 axioms.",
                             "https://x/now": "main has 2087 declarations"})
    assert cls_of(claims, "lean_declarations", "1323") == {"UNEXPLAINED"}
    assert cls_of(claims, "lean_axioms", "23") == {"UNEXPLAINED"}
    assert cls_of(claims, "lean_declarations", "2087") == {"CURRENT"}
    F = C.Findings()
    C.check_claims(claims, TRUTH, cons, F)
    titles = [f["title"] for f in F.items]
    assert any("1323" in t for t in titles) and any("23" in t for t in titles)
    assert all(f["sev"] == "P1" for f in F.items)
    assert "https://github.com/szl-holdings/lutar-lean#readme" in F.items[0]["evidence"]


def test_dated_lean_value_is_historical():
    claims, _ = classify({"https://x/": "On 2026-07-01 the corpus had 1323 declarations."})
    assert cls_of(claims, "lean_declarations", "1323") == {"HISTORICAL"}


def test_triple_without_lean_context_is_ignored():
    claims, _ = classify({"https://x/api": '{"tabs": "203/204/205", "ok": true}'})
    assert not [c for c in claims if c["key"] == "doctrine_triple"]


def test_consensus_and_dissent_for_flagships():
    claims, cons = classify({"a": "three flagships", "b": "3 flagships", "c": "4 flagships"})
    assert cons["flagships"] == "3"
    assert cls_of(claims, "flagships", "4") == {"DISSENT"}
    F = C.Findings()
    C.check_claims(claims, TRUTH, cons, F)
    assert len(F.items) == 1 and F.items[0]["sev"] == "P2" and "majority value is 3" in F.items[0]["title"]


def test_tie_has_no_consensus():
    claims, cons = classify({"a": "3 flagships", "b": "4 flagships"})
    assert cons["flagships"] is None
    assert cls_of(claims, "flagships", "3") == {"DISSENT"} and cls_of(claims, "flagships", "4") == {"DISSENT"}


def test_counts_need_org_context_and_tolerance():
    claims, _ = classify({"a": "The SZL Hub org publishes 48 public models.", "b": "We tried 12 models in a benchmark.",
                          "c": "SZLHOLDINGS has 30 public datasets.", "d": "HF estate snapshot 2026-08-31: 44 models"})
    assert cls_of(claims, "count_models", "48") == {"CURRENT"}  # within 10% of 49
    assert not [c for c in claims if c["value"] == "12"]  # no org context -> not a claim
    assert cls_of(claims, "count_datasets", "30") == {"STALE"}
    assert cls_of(claims, "count_models", "44") == {"HISTORICAL"}


def test_repo_count_accepts_total_including_archived():
    claims, _ = classify({"a": "the szl-holdings org has 94 repositories"})
    assert cls_of(claims, "count_repos", "94") == {"CURRENT"}


def test_slsa_level_normalised():
    claims, _ = classify({"a": "SLSA L1 attested + L3 roadmap", "b": "SLSA Level 1", "c": "SLSA L1"})
    # only the attested level is a claim; "+ L3 roadmap" is not
    assert {c["value"] for c in claims if c["key"] == "slsa_claimed"} == {"1"}


def test_parse_hf():
    assert C.parse_hf("https://huggingface.co/collections/SZLHOLDINGS/x-6a93") is None
    assert C.parse_hf("https://huggingface.co/SZLHOLDINGS") is None
    assert C.parse_hf("https://huggingface.co/spaces/SZLHOLDINGS") is None
    assert C.parse_hf("https://huggingface.co/spaces/SZLHOLDINGS/anatomy") == ("space", "SZLHOLDINGS/anatomy")
    assert C.parse_hf("https://huggingface.co/datasets/SZLHOLDINGS/d/tree/main") == ("dataset", "SZLHOLDINGS/d")
    assert C.parse_hf("https://huggingface.co/SZLHOLDINGS/m/resolve/main/x.bin") == ("model", "SZLHOLDINGS/m")
    assert C.parse_hf("https://huggingface.co/papers/2502.16161") is None


def test_placeholder_nodes_not_prose_dashes():
    html = "<p>a11oy — the governed AI plane — ships receipts.</p><span>—</span><td> UNAVAILABLE </td><b>CHECKING</b>" \
           "<script>x = '<i>—</i>'</script>"
    stripped = C.re.sub(r"(?is)<(script|style|template)\b[^>]*>.*?</\1\s*>", " ", html)
    assert len(C.PLACEHOLDER_NODE.findall(stripped)) == 3


def test_template_hrefs_skipped_and_scripts_stripped():
    assert C.TEMPLATE_HREF.search("${esc(n._cite)}") and C.TEMPLATE_HREF.search("%24%7Burl%7D")
    body = C.strip_code('<a href="/ok">x</a><script>el.innerHTML = `<a href="${url}">`</script>')
    assert C.re.findall(r'href\s*=\s*["\']([^"\'#\s]+)', body) == ["/ok"]


def test_freshness_uses_newest_date_and_skips_history(monkeypatch):
    F = C.Findings()
    new = (C.NOW - C.dt.timedelta(days=3)).strftime("%Y-%m-%d")
    pages = {"https://a/x": {"status": 200, "body": f'"observed_at": "2026-01-01" ... "generated_at": "{new}"'},
             "https://a/CHANGELOG.md": {"status": 200, "body": "snapshot 2020-01-01"},
             "https://a/old": {"status": 200, "body": "Estate snapshot · MEASURED · 2026-01-02"},
             "https://a/update": {"status": 200, "body": "candidate 2020-01-01 date 2020-01-01"}}
    C.freshness(pages, 14, F)
    assert [f["target"] for f in F.items] == ["https://a/old"] and F.items[0]["sev"] == "P1"


def test_provenance_normalisation_ignores_scripts_and_crlf():
    a = C._norm_lines("<html>\r\n<body>x   \r\n<script>beacon()</script></body>\r\n")
    b = C._norm_lines("<html>\n<body>x\n</body>\n")
    assert a == b


def test_redaction_and_fingerprint_stability():
    tok = "ghp_" + "A" * 36
    assert tok not in C.redact(f"Bearer {tok}") and C.redact(tok).endswith("AAAA")
    F = C.Findings()
    f1 = F.add("links", "P2", "https://a/", "Landing page is 2871 words")
    f2 = F.add("links", "P2", "https://a/", "Landing page is 3100 words")
    assert f1["fp"] == f2["fp"]


def test_write_is_utf8_and_contains_lambda(tmp_path):
    F = C.Findings()
    F.add("lean", "P3", "x", "Λ drift", "ñ …")
    data = {"pillars": C.score(F), "severity": {"P0": 0, "P1": 0, "P2": 0, "P3": 1}, "lean": {}, "counts_measured": {},
            "gh_org": "o", "hf_org": "h", "estate_state": {"github": "MEASURED"}, "claim_classes": ["CANONICAL"],
            "claims_summary": {}, "narrative": {}, "dns": {}, "http": {}, "imported": {}, "diff": None}
    C.write(tmp_path, F, data)
    memo = (tmp_path / "BOARD_MEMO.md").read_text(encoding="utf-8")
    assert "Λ" in memo and "\r\n" not in (tmp_path / "BOARD_MEMO.md").read_bytes().decode("utf-8")
    js = json.loads((tmp_path / "compass_report.json").read_text(encoding="utf-8"))
    assert js["signature"] == "UNSIGNED_HONEST" and len(js["receipt_root"]) == 64


def test_file_issues_refuses_without_confirmation(monkeypatch, capsys):
    monkeypatch.delenv(C.CONFIRM_ENV, raising=False)
    assert C.file_issues(C.Findings(), "o/.github", 5, "") == []
    assert "REFUSED" in capsys.readouterr().err


def test_surface_url():
    assert C.surface_url("github:org-profile") == "https://github.com/szl-holdings"
    assert C.surface_url("github:szl-holdings/a11oy#README") == "https://github.com/szl-holdings/a11oy#readme"
    assert C.surface_url("hf:spaces/SZLHOLDINGS/a") == "https://huggingface.co/spaces/SZLHOLDINGS/a"


def test_slsa_negations_and_roadmap_are_not_claims():
    claims, cons = classify({"a": "SLSA L3 is roadmap; we do NOT claim L3 today.", "b": "SLSA L1 honest", "c": "SLSA L1 honest",
                             "d": "banned overclaims 'SLSA L3'", "e": "[![SLSA L2 verified](https://img.shields.io/x)]",
                             "f": "SLSA **L2 verified build-provenance** (in-line, isolated builders) remains on the roadmap"})
    assert cls_of(claims, "slsa_claimed", "3") == {"NEGATED"}
    assert {c["cls"] for c in claims if c["surface"] == "f"} == {"NEGATED"}
    assert {c["cls"] for c in claims if c["surface"] == "e"} == {"DISSENT"}
    assert cons["slsa_claimed"] == "1"


def test_commercial_flagships_are_their_own_key():
    claims, cons = classify({"a": "three commercial flagships and one inference flagship", "b": "Not a fifth flagship.",
                             "c": "not a fifth flagship", "d": "Not a fourth flagship."})
    assert cls_of(claims, "commercial_flagships", "3") == {"CONSENSUS"}
    assert cons["flagships"] == "4" and cls_of(claims, "flagships", "3") == {"DISSENT"}


def test_fips_triple_and_small_scoped_values_ignored():
    claims, _ = classify({"a": "doctrine cites NIST PQC FIPS 203/204/205 for signing", "b": "round-trip preserves body (1 sorry)"})
    assert not [c for c in claims if c["key"] == "doctrine_triple"]
    assert cls_of(claims, "lean_sorries", "1") == {"SCOPED"}


def test_lean_count_uses_text_mode_line_splitting():
    n = C.lean_count([("Lutar/A.lean", "-- sorry\x0cexample := sorry\r\ntheorem t : True := trivial\r")])
    assert n["sorries_raw"] == 2 and n["sorries_noncomment"] == 0 and n["declarations"] == 1


def test_dmarc_policy_reads_p_not_sp():
    assert C.dmarc_policy(['"v=DMARC1; p=none; sp=reject"']) == "none"
    assert C.dmarc_policy(['"v=DMARC1; p=reject; sp=reject; adkim=s"']) == "reject"
    assert C.dmarc_policy([]) == ""


def test_dns_failure_is_unavailable_not_absent(monkeypatch):
    monkeypatch.setattr(C, "jget", lambda *a, **k: (0, None))
    F = C.Findings()
    out = C.dns_posture(F, [], ["szlholdings.com"])
    assert all(v["state"] == "UNAVAILABLE" for v in out.values())
    assert not [f for f in F.items if "DMARC" in f["title"] or "SPF" in f["title"]]


def test_iri_is_encoded_not_dropped():
    assert C._iri("https://example.com/ñandú?q=é") == "https://example.com/%C3%B1and%C3%BA?q=%C3%A9"
    assert C._iri("https://münchen.de/").startswith("https://xn--mnchen-3ya.de/")


def test_provenance_keeps_changed_href_lines_visible(monkeypatch):
    served = "<html>\n<a href=\"/pricing\">Pricing</a>\n<link href=\"/app.1234abcd5678.css\">\n</html>\n"
    canon = "<html>\n<a href=\"/contact\">Contact</a>\n<link href=\"/app.css\">\n</html>\n"
    pages = {C.LANDING_PAIR[0]: served, C.LANDING_PAIR[1]: canon}
    monkeypatch.setattr(C, "fetch", lambda u, **k: {"status": 200, "body": pages[u]})
    F = C.Findings()
    res = C.provenance(F)
    assert res["undeclared_delta_lines"] == 2  # the changed <a href> line (both sides); the hashed CSS name is a declared delta


def test_guarded_turns_crash_into_finding():
    F = C.Findings()
    assert C.guarded(F, "boom", "web", lambda: 1 / 0, default="d") == "d"
    assert F.items[0]["sev"] == "P1" and "crashed" in F.items[0]["title"] and "web" in C.INCOMPLETE
    C.INCOMPLETE.discard("web")


def test_thousands_separators_are_whole_numbers():
    claims, _ = classify({"a": "the SZL org has 2,048 repositories", "b": "Lean main has 2,119 declarations"})
    assert {c["value"] for c in claims if c["key"] == "count_repos"} == {"2048"}
    assert {c["value"] for c in claims if c["key"] == "lean_declarations"} == {"2119"}


def test_slsa_table_cells_and_banned_lists_are_negated():
    claims, _ = classify({"k1": "| SLSA L3 | ❌ Not claimed |", "k2": "| SLSA **L3** | 🛣️ **Roadmap** — hardened builder |",
                          "g": "flags banned overclaims 'zero sorries'/'SLSA L3'/'100% proven'",
                          "l": "The platform is not SLSA L3, FedRAMP, or CMMC", "ok": "SLSA L1 honest"})
    assert {c["cls"] for c in claims if c["key"] == "slsa_claimed" and c["value"] == "3"} == {"NEGATED"}


def test_flagship_modules_are_not_flagship_counts():
    claims, _ = classify({"sdk": "One client, five flagship modules, each typed.", "p": "Two flagships. Bound packages stay packages."})
    assert {c["value"] for c in claims if c["key"] == "flagships"} == {"2"}


def test_escaped_em_dash_and_tier_labels_are_not_counts():
    claims, _ = classify({"j": '"title": "SZL Holdings \\u2014 Models & Kernel Contracts"',
                          "g": "45 Spaces tiered: 5 FLAGSHIP (recommended), 38 LAB"})
    assert not [c for c in claims if c["value"] == "2014"]
    assert not [c for c in claims if c["key"] == "flagships"]


def test_blockquote_linebreak_keeps_roadmap_negation():
    claims, _ = classify({"u": "SLSA **L2 verified build-provenance** (in-line,\n> isolated builders) remains on the roadmap."})
    assert {c["cls"] for c in claims if c["key"] == "slsa_claimed"} == {"NEGATED"}
