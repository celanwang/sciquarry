import copy
import contextlib
import io
import json
from pathlib import Path
import tempfile
import unittest

from sciquarry.evaluate import sha256
from sciquarry.regression import compare, main


SAMPLES=[{'id':'dev-1','question':'Question?','evidence':[{'passage_id':'P02:1:p1'}]}]
REVIEWS=[{'type':'metadata','review_kind':'assistant_preliminary_not_expert'},
         {'sample_id':'dev-1','reviewer_kind':'assistant','review_status':'assistant_preliminary_domain_review_pending',
          'findings':[{'finding_id':'dev-1:1#1'}]}]
CASES=[{'type':'metadata','samples_sha256':'sample-sha'},
       {'type':'case','id':'reg-1','sample_id':'dev-1','finding_ids':['dev-1:1#1'],
        'evidence_ids':['P02:1:p1'],'checks_for_human_review':['Check source.'],
        'review_status':'assistant_preliminary_domain_review_pending'}]
META={'sample_sha256':'sample-sha','index_sha256':'index-sha','model':'model',
      'base_url':'http://localhost:8080/v1','no_thinking':True,'temperature':0,'max_tokens':1024}
ANSWER={'sample_id':'dev-1','question':'Question?','provided_passage_ids':['P02:1:p1'],
        'answer':'An answer.','citation_status':'missing','unknown_citations':[],
        'finish_reason':'stop','system_fingerprint':'test-runtime'}


class RegressionTest(unittest.TestCase):
    def setUp(self):
        self.cases=copy.deepcopy(CASES); self.samples=copy.deepcopy(SAMPLES); self.reviews=copy.deepcopy(REVIEWS)
        self.before=copy.deepcopy(ANSWER); self.after=copy.deepcopy(ANSWER)
        self.a_meta=copy.deepcopy(META); self.b_meta=copy.deepcopy(META)

    def compare(self):
        return compare(self.cases,self.samples,self.reviews,self.a_meta,{'dev-1':self.before},
                       self.b_meta,{'dev-1':self.after})

    def test_comparison_never_creates_an_automatic_verdict(self):
        self.after['answer']='A changed answer.'
        row=self.compare()[0]
        self.assertFalse(row['text_identical'])
        self.assertEqual(row['comparison_status'],'pending_manual_review')
        self.assertIsNone(row['verdict'])
        self.assertTrue(row['service_fingerprint_verified'])

    def test_rejects_different_config_and_evidence(self):
        self.b_meta['temperature']=0.7
        with self.assertRaisesRegex(ValueError,'configuration mismatch'):
            self.compare()
        self.b_meta['temperature']=0
        self.after['provided_passage_ids']=['P02:2:p1']
        with self.assertRaisesRegex(ValueError,'evidence differs'):
            self.compare()

    def test_rejects_unrelated_finding_and_changed_service(self):
        self.cases[1]['finding_ids']=['other#1']
        with self.assertRaisesRegex(ValueError,'finding IDs'):
            self.compare()
        self.cases[1]['finding_ids']=['dev-1:1#1']
        self.after['system_fingerprint']='other-runtime'
        with self.assertRaisesRegex(ValueError,'fingerprint changed'):
            self.compare()

    def test_cli_pins_inputs_and_refuses_overwrite(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp)
            def write(name, rows):
                path=root/name
                path.write_text(''.join(json.dumps(r)+'\n' for r in rows))
                return path
            samples=write('samples.jsonl',self.samples)
            reviews=write('reviews.jsonl',self.reviews)
            index=write('index.jsonl',[{'id':'P02:1:p1'}])
            meta=copy.deepcopy(META)
            meta.update(type='metadata',mode='answer',sample_count=1,
                        sample_sha256=sha256(samples),index_sha256=sha256(index))
            summary={'type':'summary','successes':1,'failures':0}
            before=write('before.jsonl',[meta,{'type':'result',**self.before},summary])
            after=write('after.jsonl',[meta,{'type':'result',**self.after},summary])
            cases=copy.deepcopy(self.cases)
            cases[0].update(samples_sha256=sha256(samples),assistant_review_sha256=sha256(reviews),
                            baseline_answer_sha256=sha256(before))
            case_file=write('cases.jsonl',cases)
            out=root/'comparison.jsonl'
            args=['--cases',str(case_file),'--samples',str(samples),'--reviews',str(reviews),
                  '--before',str(before),'--after',str(after),'--index',str(index),'--output',str(out)]
            with contextlib.redirect_stdout(io.StringIO()),contextlib.redirect_stderr(io.StringIO()):
                self.assertEqual(main(args),0)
                previous=out.read_text()
                self.assertEqual(main(args),1)
            self.assertEqual(out.read_text(),previous)
            after.write_text(after.read_text().replace('Question?', 'Other question?'))
            args[args.index('--output')+1]=str(root/'invalid.jsonl')
            with contextlib.redirect_stderr(io.StringIO()):
                self.assertEqual(main(args),1)
            self.assertFalse((root/'invalid.jsonl').exists())

    def test_missing_runtime_fingerprint_is_marked_unverified(self):
        self.after['system_fingerprint']=None
        self.assertFalse(self.compare()[0]['service_fingerprint_verified'])


if __name__=='__main__':
    unittest.main()
