"""Negative controls for the offline, non-authorizing receipt gallery."""
import hashlib
import importlib.util
import json
from pathlib import Path
import tempfile
import unittest

FILE = Path(__file__).resolve().parents[1] / 'receipt_gallery.py'
spec = importlib.util.spec_from_file_location('receipt_gallery', FILE)
gallery = importlib.util.module_from_spec(spec)
spec.loader.exec_module(gallery)

class ReceiptGalleryTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        (self.root/'receipts').mkdir()
        self.record = {'kind':'szl.estate-battery/test','state':'MEASURED','model':'SZLHOLDINGS/synthetic-test','base':'example/base','score':'1/2','rows':[{'id':'a1','kind':'answerable','verdict':'PASS','abstained':False},{'id':'u1','kind':'unanswerable','verdict':'FAIL','abstained':False}]}
        self.revision = '1'*40
        self.write()
    def write(self):
        self.record['receipt_sha256'] = gallery.receipt_body_digest(self.record)
        self.raw = json.dumps(self.record, indent=2).encode()
        (self.root/'receipts/test.json').write_bytes(self.raw)
        self.entry = {'path':'receipts/test.json','file_sha256':hashlib.sha256(self.raw).hexdigest(),'size_bytes':len(self.raw),'url':'https://huggingface.co/datasets/SZLHOLDINGS/frontier-54-runs/resolve/'+self.revision+'/benchmark/test.json'}
        self.manifest = {'schema':gallery.SCHEMA,'revision':self.revision,'observed_at':'2026-11-13T00:00:00Z','entries':[self.entry]}
        self.path = self.root/'receipt-manifest.json'
        self.path.write_text(json.dumps(self.manifest),encoding='utf-8')
    def test_valid_receipt_keeps_authority_false(self):
        result=gallery.load_gallery(self.path)
        self.assertFalse(result['execution_authorized'])
        self.assertEqual(result['records'][0]['model_revision_binding'],'NOT_ESTABLISHED')
    def test_tampered_file_rejected(self):
        (self.root/'receipts/test.json').write_bytes(self.raw+b' ')
        with self.assertRaises(gallery.EvidenceError):gallery.load_gallery(self.path)
    def test_embedded_digest_rejected_even_after_raw_rehash(self):
        self.record['receipt_sha256']='0'*64
        raw=json.dumps(self.record).encode();(self.root/'receipts/test.json').write_bytes(raw)
        self.entry.update(file_sha256=hashlib.sha256(raw).hexdigest(),size_bytes=len(raw))
        with self.assertRaises(gallery.EvidenceError):gallery.inspect_entry(self.root,self.entry,self.revision)
    def test_duplicate_probe_rejected(self):
        self.record['rows'][1]['id']='a1';self.write()
        with self.assertRaises(gallery.EvidenceError):gallery.load_gallery(self.path)
    def test_score_not_recounted_to_a_more_favorable_result(self):
        self.record['score']='2/2';self.write()
        with self.assertRaises(gallery.EvidenceError):gallery.load_gallery(self.path)
    def test_empty_population_rejected(self):
        self.record.update(score='0/0',rows=[]);self.write()
        with self.assertRaises(gallery.EvidenceError):gallery.load_gallery(self.path)
    def test_boolean_count_is_not_byte_count(self):
        self.entry['size_bytes']=True
        with self.assertRaises(gallery.EvidenceError):gallery.inspect_entry(self.root,self.entry,self.revision)
    def test_mutable_or_foreign_url_rejected(self):
        for url in (self.entry['url'].replace(self.revision,'main'),self.entry['url'].replace('SZLHOLDINGS','other')):
            with self.subTest(url=url),self.assertRaises(gallery.EvidenceError):gallery.inspect_entry(self.root,{**self.entry,'url':url},self.revision)
    def test_path_traversal_rejected(self):
        with self.assertRaises(gallery.EvidenceError):gallery.inspect_entry(self.root,{**self.entry,'path':'../test.json'},self.revision)
    def test_duplicate_json_and_nonfinite_rejected(self):
        for raw in (b'{"x":1,"x":2}',b'{"x":NaN}',b'{"x":Infinity}',b'\xff',b''):
            with self.subTest(raw=raw),self.assertRaises(gallery.EvidenceError):gallery.strict_json(raw)
    def test_missing_method_metadata_is_not_invented(self):
        row=gallery.load_gallery(self.path)['records'][0]
        self.assertIsNone(row['vocabulary_terms'])
        self.assertEqual(row['curriculum'],'NOT_RECORDED')
    def test_html_escaped(self):
        self.record['model']='<script>alert(1)</script>';self.write()
        rendered=gallery.render_gallery(gallery.load_gallery(self.path))
        self.assertNotIn('<script>',rendered)
        self.assertIn('&lt;script&gt;',rendered)
    def test_semantic_meter_has_numeric_denominator(self):
        rendered=gallery.render_gallery(gallery.load_gallery(self.path))
        self.assertIn('max="2" value="1"',rendered)
        self.assertIn('not rank models',rendered)
    def test_duplicate_receipt_rejected(self):
        self.manifest['entries']*=2;self.path.write_text(json.dumps(self.manifest))
        with self.assertRaises(gallery.EvidenceError):gallery.load_gallery(self.path)
    def test_empty_manifest_rejected(self):
        self.manifest['entries']=[];self.path.write_text(json.dumps(self.manifest))
        with self.assertRaises(gallery.EvidenceError):gallery.load_gallery(self.path)
    def test_render_is_deterministic(self):
        data=gallery.load_gallery(self.path)
        self.assertEqual(gallery.render_gallery(data),gallery.render_gallery(data))

if __name__ == '__main__':unittest.main()
