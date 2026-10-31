import copy
import json
from pathlib import Path
import tempfile
import unittest

from sciquarry import sft


class SFTDataTests(unittest.TestCase):
    def setUp(self):
        self.records = sft.read_jsonl(Path('data/sft/synthetic_smoke.jsonl'))

    def reviewed(self):
        rows = copy.deepcopy(self.records)
        for i, row in enumerate(rows):
            row['kind'] = 'reviewed'
            for item in row['evidence']:
                item.update(source_url='https://example.org/source', locator='section 1',
                            license='test license', source_sha256=str(i + 1) * 64, training_use_permitted=True)
            row['review'] = {'status': 'approved', 'reviewer_kind': 'human_domain_expert',
                             'reviewer': 'test reviewer', 'reviewed_at': '2026-01-01',
                             'content_sha256': sft.digest_record(row)}
        return rows

    def test_valid_synthetic_and_reviewed(self):
        self.assertEqual(sft.validate(self.records, 'synthetic'), {'train': 1, 'valid': 1, 'test': 1})
        sft.validate(self.reviewed(), 'reviewed')

    def test_review_required_and_bound_to_content(self):
        rows = self.reviewed()
        rows[0]['answer'] += ' changed'
        with self.assertRaisesRegex(ValueError, 'digest mismatch'):
            sft.validate(rows, 'reviewed')
        rows = self.reviewed()
        rows[0]['review']['reviewer_kind'] = 'assistant'
        with self.assertRaisesRegex(ValueError, 'expert approval'):
            sft.validate(rows, 'reviewed')

    def test_training_permission_and_reserved_source(self):
        rows = self.reviewed(); rows[0]['evidence'][0]['training_use_permitted'] = False
        with self.assertRaisesRegex(ValueError, 'permission'):
            sft.validate(rows, 'reviewed')
        rows = self.reviewed()
        with self.assertRaisesRegex(ValueError, 'reserved'):
            sft.validate(rows, 'reviewed', {'SYN01'})
        self.assertTrue({'P02', 'P05'}.issubset(sft.reserved_sources()))
        rows = self.reviewed()
        with self.assertRaisesRegex(ValueError, 'digest is reserved'):
            sft.validate(rows, 'reviewed', reserved_hashes={rows[0]['evidence'][0]['source_sha256']})
        self.assertTrue(sft.reserved_source_hashes())

    def test_split_and_question_leakage(self):
        rows = copy.deepcopy(self.records); rows[1]['group_id'] = rows[0]['group_id']
        with self.assertRaisesRegex(ValueError, 'group spans'):
            sft.validate(rows, 'synthetic')
        rows = copy.deepcopy(self.records); rows[1]['question'] = rows[0]['question']
        with self.assertRaisesRegex(ValueError, 'duplicate question'):
            sft.validate(rows, 'synthetic')
        rows = copy.deepcopy(self.records); rows[1]['evidence'][0]['source_id'] = 'SYN01'; rows[1]['evidence'][0]['id'] = 'SYN01:1:p2'
        with self.assertRaisesRegex(ValueError, 'source spans'):
            sft.validate(rows, 'synthetic')

    def test_source_digest_and_evidence_must_not_cross_splits(self):
        rows = self.reviewed()
        rows[1]['evidence'][0]['source_sha256'] = rows[0]['evidence'][0]['source_sha256']
        with self.assertRaisesRegex(ValueError, 'source digest spans'):
            sft.validate(rows, 'reviewed')
        rows = copy.deepcopy(self.records)
        rows[1]['evidence'][0]['text'] = rows[0]['evidence'][0]['text']
        with self.assertRaisesRegex(ValueError, 'identical evidence spans'):
            sft.validate(rows, 'synthetic')

    def test_invalid_citations(self):
        rows = copy.deepcopy(self.records); rows[0]['answer'] = '答案 [SYN99:1:p1]'
        with self.assertRaisesRegex(ValueError, 'citations'):
            sft.validate(rows, 'synthetic')

    def test_prepared_data_integrity_and_no_overwrite(self):
        with tempfile.TemporaryDirectory() as d:
            data = Path(d) / 'prepared'
            sft.prepare(Path('data/sft/synthetic_smoke.jsonl'), data, 'synthetic', ())
            sft.verify_prepared(data)
            with self.assertRaises(FileExistsError):
                sft.prepare(Path('data/sft/synthetic_smoke.jsonl'), data, 'synthetic', ())
            (data / 'train.jsonl').write_text('{}\n')
            with self.assertRaisesRegex(ValueError, 'changed'):
                sft.verify_prepared(data)

    def test_forged_manifest_does_not_hide_derived_message_change(self):
        with tempfile.TemporaryDirectory() as d:
            data = Path(d) / 'prepared'
            sft.prepare(Path('data/sft/synthetic_smoke.jsonl'), data, 'synthetic', ())
            path = data / 'train.jsonl'; path.write_text('{}\n')
            manifest_path = data / 'manifest.json'
            manifest = json.loads(manifest_path.read_text()); manifest['files']['train.jsonl'] = sft.sha256(path)
            manifest_path.write_text(json.dumps(manifest))
            with self.assertRaisesRegex(ValueError, 'do not match'):
                sft.verify_prepared(data)


if __name__ == '__main__':
    unittest.main()
