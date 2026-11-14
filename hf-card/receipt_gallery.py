#!/usr/bin/env python3
"""Offline presentation of pinned public receipts; never qualifies a model."""
from __future__ import annotations
import argparse
import hashlib
import html
import json
from pathlib import Path
import re

SCHEMA = 'szl.receipt-gallery-input/v1'
MAX_BYTES = 1_000_000
SHA256 = re.compile(r'[0-9a-f]{64}')
SHA40 = re.compile(r'[0-9a-f]{40}')

class EvidenceError(ValueError):
    pass

def require(condition: bool, reason: str) -> None:
    if not condition:
        raise EvidenceError(reason)

def unique_object(pairs):
    result = {}
    for key, value in pairs:
        require(key not in result, 'duplicate JSON member')
        result[key] = value
    return result

def strict_json(raw: bytes):
    require(0 < len(raw) <= MAX_BYTES, 'empty or oversized JSON')
    try:
        return json.loads(raw.decode('utf-8'), object_pairs_hook=unique_object,
                          parse_constant=lambda value: (_ for _ in ()).throw(EvidenceError('nonfinite JSON')))
    except (ValueError, UnicodeError, RecursionError) as exc:
        raise EvidenceError('invalid JSON') from exc

def receipt_body_digest(record: dict) -> str:
    # Matches this receipt family's existing convention, not a new universal format.
    body = {k: v for k, v in record.items() if k != 'receipt_sha256'}
    return hashlib.sha256(json.dumps(body, sort_keys=True, ensure_ascii=True,
                                    allow_nan=False).encode('utf-8')).hexdigest()

def inspect_entry(root: Path, entry: dict, revision: str) -> dict:
    require(type(entry) is dict and set(entry) == {'path', 'file_sha256', 'size_bytes', 'url'}, 'invalid manifest entry')
    path = entry['path']
    require(type(path) is str and re.fullmatch(r'receipts/[A-Za-z0-9_.-]+[.]json', path) is not None, 'invalid receipt path')
    expected_url = 'https://huggingface.co/datasets/SZLHOLDINGS/frontier-54-runs/resolve/' + revision + '/benchmark/' + Path(path).name
    require(entry['url'] == expected_url, 'wrong or mutable receipt URL')
    require(type(entry['file_sha256']) is str and SHA256.fullmatch(entry['file_sha256']) is not None, 'invalid raw-file digest')
    require(type(entry['size_bytes']) is int and 0 < entry['size_bytes'] <= MAX_BYTES, 'invalid byte count')
    target = root / path
    require(not target.is_symlink() and target.resolve().is_relative_to(root.resolve()), 'receipt escapes source directory')
    raw = target.read_bytes()
    require(len(raw) == entry['size_bytes'], 'receipt byte count mismatch')
    require(hashlib.sha256(raw).hexdigest() == entry['file_sha256'], 'raw-file digest mismatch')
    data = strict_json(raw)
    require(type(data) is dict and type(data.get('receipt_sha256')) is str, 'missing embedded digest')
    require(SHA256.fullmatch(data['receipt_sha256']) is not None, 'invalid embedded digest')
    require(receipt_body_digest(data) == data['receipt_sha256'], 'embedded digest mismatch')
    require(data.get('state') == 'MEASURED', 'unsupported receipt state')
    score = data.get('score')
    require(type(score) is str and re.fullmatch(r'\d+/[1-9]\d*', score) is not None, 'invalid recorded score')
    passed, count = map(int, score.split('/'))
    rows = data.get('rows')
    require(type(rows) is list and 0 < count <= 1000 and len(rows) == count, 'empty or incomplete population')
    ids = []
    for row in rows:
        require(type(row) is dict and type(row.get('id')) is str and row['id'], 'missing probe identity')
        ids.append(row['id'])
        require(row.get('verdict') in {'PASS', 'FAIL'} and type(row.get('abstained')) is bool, 'unsupported probe verdict')
        require(row.get('kind') in {'answerable', 'unanswerable'}, 'unsupported probe class')
    require(len(set(ids)) == len(ids), 'duplicate probe identity')
    require(sum(row['verdict'] == 'PASS' for row in rows) == passed, 'recorded score disagrees with rows')
    require(type(data.get('model')) is str and 0 < len(data['model']) < 256, 'missing model identity')
    require(type(data.get('base')) is str and data['base'], 'missing base identity')
    return {'model': data['model'], 'base': data['base'], 'passed': passed, 'count': count,
            'recorded_at': data.get('ts', 'NOT_RECORDED'), 'curriculum': data.get('curriculum', 'NOT_RECORDED'),
            'vocabulary_terms': len(data['abstention_vocabulary']) if type(data.get('abstention_vocabulary')) is list else None,
            'url': entry['url'], 'file_sha256': entry['file_sha256'], 'receipt_sha256': data['receipt_sha256'],
            'rows': [{'id': r['id'], 'kind': r['kind'], 'verdict': r['verdict'], 'abstained': r['abstained']} for r in rows],
            'model_revision_binding': 'NOT_ESTABLISHED', 'runtime_readiness': 'NOT_ESTABLISHED',
            'signature_verification': 'NOT_PERFORMED', 'causal_comparison': 'NOT_ESTABLISHED'}

def load_gallery(manifest: Path) -> dict:
    document = strict_json(manifest.read_bytes())
    require(type(document) is dict and set(document) == {'schema', 'revision', 'observed_at', 'entries'}, 'invalid gallery manifest')
    require(document['schema'] == SCHEMA, 'unsupported gallery schema')
    require(type(document['revision']) is str and SHA40.fullmatch(document['revision']) is not None, 'immutable snapshot required')
    require(type(document['observed_at']) is str and document['observed_at'], 'missing observation time')
    entries = document['entries']
    require(type(entries) is list and 0 < len(entries) <= 100, 'empty or excessive receipt set')
    rows = [inspect_entry(manifest.parent, e, document['revision']) for e in entries]
    require(len({e['url'] for e in rows}) == len(rows), 'duplicate receipt URL')
    return {'revision': document['revision'], 'observed_at': document['observed_at'], 'records': rows,
            'scope': 'RAW_BYTES_EMBEDDED_DIGEST_AND_RECORDED_TOTALS_ONLY', 'execution_authorized': False}

STYLE = '''body{margin:0;background:#090b10;color:#f2f0e9;font:16px/1.6 system-ui,sans-serif}main{max-width:1120px;margin:auto;padding:36px 20px 64px}a{color:#8fd9d5;text-underline-offset:4px}a:focus-visible,summary:focus-visible{outline:3px solid #8fd9d5;outline-offset:4px}.eyebrow{font:12px ui-monospace,monospace;text-transform:uppercase;letter-spacing:.16em;color:#a7aebc}h1{font-size:clamp(32px,6vw,64px);line-height:1.06;max-width:850px;letter-spacing:-.035em}h2{font-size:21px;overflow-wrap:anywhere;margin:0 0 8px}.intro{max-width:820px;font-size:18px;color:#a7aebc}.grid{display:grid;grid-template-columns:repeat(auto-fit,minmax(min(100%,340px),1fr));gap:20px}.record{min-width:0;border:1px solid #343c49;border-radius:16px;background:#11151d;padding:24px}.boundary{border-left:3px solid #8fd9d5;padding:16px 20px;margin:28px 0 40px;background:#11151d}.score{font-size:38px;font-weight:700;font-variant-numeric:tabular-nums}.muted{color:#a7aebc}.small{font-size:13px}code{font:12px ui-monospace,monospace;overflow-wrap:anywhere}meter{width:100%;height:20px;margin:6px 0 14px}table{width:100%;border-collapse:collapse;font-size:13px}th,td{padding:8px 4px;text-align:left;border-bottom:1px solid #343c49;overflow-wrap:anywhere}caption{text-align:left;color:#a7aebc;margin-bottom:8px}summary{cursor:pointer;padding:12px 0;min-height:24px}p,dd{overflow-wrap:anywhere}nav{display:flex;flex-wrap:wrap;gap:24px}nav a{display:inline-flex;align-items:center;min-height:44px}dt{color:#a7aebc;font-size:13px}dd{margin:0 0 12px}footer{margin-top:40px;border-top:1px solid #343c49;padding-top:20px;color:#a7aebc}*{box-sizing:border-box}@media(prefers-reduced-motion:reduce){*{scroll-behavior:auto}}'''

def render_gallery(gallery: dict) -> str:
    esc = lambda value: html.escape(str(value), quote=True)
    cards = []
    for i, row in enumerate(gallery['records']):
        table = ''.join('<tr><td>'+esc(r['id'])+'</td><td>'+esc(r['kind'])+'</td><td>'+esc(r['verdict'])+'</td><td>'+esc(r['abstained'])+'</td></tr>' for r in row['rows'])
        vocabulary = str(row['vocabulary_terms']) if row['vocabulary_terms'] is not None else 'Not recorded'
        cards.append(f'''<article class="record" id="receipt-{i}"><p class="eyebrow">Archived harness verdicts</p><h2>{esc(row['model'])}</h2><p class="muted small">Base: {esc(row['base'])}</p><div class="score">{row['passed']} / {row['count']}</div><label for="result-{i}" class="small">Recorded PASS verdicts among {row['count']} probes</label><meter id="result-{i}" min="0" max="{row['count']}" value="{row['passed']}">{row['passed']} of {row['count']}</meter><p class="small">Not a model accuracy estimate or deployment qualification.</p><p><a href="{esc(row['url'])}">Inspect pinned receipt</a></p><details><summary>Probe outcomes and provenance</summary><table><caption>Recorded labels; not independently rescored answers</caption><thead><tr><th>Probe</th><th>Class</th><th>Verdict</th><th>Abstained</th></tr></thead><tbody>{table}</tbody></table><dl><dt>Recorded at</dt><dd>{esc(row['recorded_at'])}</dd><dt>Curriculum</dt><dd>{esc(row['curriculum'])}</dd><dt>Abstention vocabulary terms</dt><dd>{esc(vocabulary)}</dd><dt>Raw-file SHA-256</dt><dd><code>{row['file_sha256']}</code></dd><dt>Embedded receipt digest (not a signature)</dt><dd><code>{row['receipt_sha256']}</code></dd></dl><p class="small muted">The receipt does not establish the evaluated immutable model revision, full-response capture, matched decoding, independent repeated trials, or present runtime readiness.</p></details></article>''')
    return f'''<!doctype html><html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><meta name="color-scheme" content="dark"><title>SZL | Receipt evidence</title><style>{STYLE}</style></head><body><main><nav aria-label="Evidence navigation"><a href="./index.html">SZL Holdings</a><a href="./receipt-manifest.json">Data manifest</a><a href="https://github.com/szl-holdings/.github">Source</a></nav><p class="eyebrow">Research evidence / reproducible inspection</p><h1>Every result has a boundary.</h1><p class="intro">Inspect the counts, then the method. These panels visualize recorded harness verdicts from immutable public receipts. They do not rank models or establish a general law of model behavior.</p><div class="boundary"><strong>{len(cards)} receipt files checked.</strong> Raw bytes, embedded digests, probe identities, and recorded totals are checked offline. This is not a signature verification, independent reproduction, or production approval.<p class="small">Observed: {esc(gallery['observed_at'])}<br>Dataset revision: <code>{gallery['revision']}</code></p><p class="small">Conditions differ in base model, curriculum and scoring metadata. Equal totals can conceal different probe outcomes. No cross-condition causal conclusion is asserted.</p></div><div class="grid">{''.join(cards)}</div><footer>Control before action. Evidence after. <a href="https://a11oy.net">Proof and limitations</a>. Every original record is retained unchanged; this presentation grants no execution authority.</footer></main></body></html>'''

def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--manifest', type=Path, required=True)
    parser.add_argument('--out', type=Path, required=True)
    parser.add_argument('--check', action='store_true')
    args = parser.parse_args()
    try:
        output = render_gallery(load_gallery(args.manifest))
        if args.check:
            require(args.out.read_text(encoding='utf-8') == output, 'rendered gallery drift')
        else:
            args.out.write_text(output, encoding='utf-8', newline='')
        return 0
    except (EvidenceError, OSError) as exc:
        print('receipt-gallery: '+str(exc))
        return 1

if __name__ == '__main__':
    raise SystemExit(main())
