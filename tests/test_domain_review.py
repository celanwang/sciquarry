import csv
import json
from pathlib import Path
import tempfile
import unittest

from sciquarry import domain_review as dr


class DomainReviewTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(); self.root = Path(self.tmp.name)
        self.samples = self.root / 'samples.jsonl'; self.index = self.root / 'index.jsonl'; self.packet = self.root / 'packet'
        sample = {'id': 'draft-1', 'question': 'Question?', 'answerability': 'answerable',
                  'reference_answer': 'Draft answer.', 'evidence': [{'passage_id': 'S:1:p1', 'source_id': 'S', 'source_sha256': 'a'*64, 'url': 'https://example.org'}],
                  'review': {'status': 'pending_domain_review'}}
        passage = {'id': 'S:1:p1', 'source_id': 'S', 'source_sha256': 'a'*64, 'source_url': 'https://example.org', 'section_path': ['Methods'], 'text': 'Fictional text.'}
        self.samples.write_text(json.dumps(sample) + '\n'); self.index.write_text(json.dumps(passage) + '\n')
        dr.create_packet([self.samples], [self.index], self.packet)

    def tearDown(self): self.tmp.cleanup()

    def edit(self, **updates):
        path = self.packet / 'reviews.csv'
        with path.open(encoding='utf-8-sig', newline='') as f: rows = list(csv.DictReader(f))
        rows[0].update(updates)
        with path.open('w', encoding='utf-8-sig', newline='') as f:
            writer = csv.DictWriter(f, fieldnames=dr.FIELDS); writer.writeheader(); writer.writerows(rows)

    def test_exported_review_is_pending(self):
        summary = dr.check_packet(self.packet)
        self.assertEqual(summary['decisions']['pending'], 1)
        self.assertEqual(summary['decisions']['approve'], 0)
        with self.assertRaises(FileExistsError): dr.create_packet([self.samples], [self.index], self.packet)

    def test_complete_review_and_conflicting_checklist(self):
        values = {'decision': 'approve', 'reviewer': 'test person', 'reviewer_background': 'test',
                  'reviewed_at': '2026-10-31', 'rationale': 'test judgment'}
        values.update({'check_' + k: 'pass' for k in dr.CHECKS})
        self.edit(**values)
        self.assertEqual(dr.check_packet(self.packet)['decisions']['approve'], 1)
        self.edit(check_evidence_support='needs_change')
        with self.assertRaisesRegex(ValueError, 'conflicts'): dr.check_packet(self.packet)

    def test_revise_requires_corrected_answer(self):
        values = {'decision': 'revise', 'reviewer': 'test person', 'reviewer_background': 'test',
                  'reviewed_at': '2026-10-31', 'rationale': 'test judgment'}
        values.update({'check_' + k: 'pass' for k in dr.CHECKS})
        self.edit(**values)
        with self.assertRaisesRegex(ValueError, 'proposed changes'): dr.check_packet(self.packet)
        self.edit(proposed_changes='clarify the question scope')
        self.assertEqual(dr.check_packet(self.packet)['decisions']['revise'], 1)

    def test_packet_tampering_and_changed_ids_fail(self):
        (self.packet / 'cases.jsonl').write_text('{}\n')
        with self.assertRaisesRegex(ValueError, 'content changed'): dr.check_packet(self.packet)
        # The original packet cannot be overwritten to disguise changes.
        with self.assertRaises(FileExistsError): dr.create_packet([self.samples], [self.index], self.packet)

    def test_mismatched_source_url_fails_export(self):
        row = json.loads(self.samples.read_text())
        row['evidence'][0]['url'] = 'https://wrong.example.org'
        self.samples.write_text(json.dumps(row) + '\n')
        with self.assertRaisesRegex(ValueError, 'URL does not match'):
            dr.create_packet([self.samples], [self.index], self.root / 'other')

    def test_provenance_mismatch_fails_export(self):
        passage = json.loads(self.index.read_text()); passage['source_sha256'] = 'b'*64
        self.index.write_text(json.dumps(passage) + '\n')
        with self.assertRaisesRegex(ValueError, 'provenance mismatch'):
            dr.create_packet([self.samples], [self.index], self.root / 'other')


if __name__ == '__main__': unittest.main()
