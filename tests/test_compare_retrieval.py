import contextlib
import io
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from sciquarry.compare_retrieval import historical_search, main


class ComparisonTest(unittest.TestCase):
    def test_rejects_non_commit_revision(self):
        with self.assertRaisesRegex(ValueError, 'hexadecimal commit'):
            historical_search('--help')

    def test_compares_same_evidence_and_does_not_overwrite(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp)
            sample={'id':'candidate','question':'example','answerability':'answerable',
                    'evidence':[{'passage_id':'P05:1:p1','source_id':'P05','source_sha256':'abc'}]}
            record={'id':'P05:1:p1','source_id':'P05','source_sha256':'abc',
                    'section_path':['Results'],'text':'example'}
            (root/'samples.jsonl').write_text(json.dumps(sample)+'\n')
            (root/'index.jsonl').write_text(json.dumps(record)+'\n')
            out=root/'comparison.jsonl'
            args=['--samples',str(root/'samples.jsonl'),'--index',str(root/'index.jsonl'),
                  '--baseline-revision','2ffeae8','--output',str(out)]
            baseline=lambda records, query, top_k: []
            with patch('sciquarry.compare_retrieval.historical_search',return_value=(baseline,'old-hash')):
                with contextlib.redirect_stdout(io.StringIO()), contextlib.redirect_stderr(io.StringIO()):
                    self.assertEqual(main(args),0)
                    self.assertEqual(main(args),1)
            rows=[json.loads(line) for line in out.read_text().splitlines()]
            self.assertEqual(rows[-1]['before_all'],0)
            self.assertEqual(rows[-1]['after_all'],1)
            self.assertEqual(rows[1]['expected'],['P05:1:p1'])


if __name__=='__main__':
    unittest.main()
