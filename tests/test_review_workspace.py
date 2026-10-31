import contextlib
import io
import json
import tempfile
import unittest
from pathlib import Path

from sciquarry.evaluate import sha256
from sciquarry.review_workspace import load_context, main


def write_jsonl(path, rows):
    path.write_text(''.join(json.dumps(x, ensure_ascii=False) + '\n' for x in rows))


class ReviewWorkspaceTest(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.index = self.root / 'index.jsonl'
        self.answers = self.root / 'answers.jsonl'
        self.candidates = self.root / 'candidates.jsonl'
        self.reviews = self.root / 'reviews.jsonl'
        self.record = {'id':'P02:1:p1', 'source_id':'P02', 'source_sha256':'source-hash',
                       'source_url':'https://example.org/source', 'section_path':['Results'],
                       'paragraph':1, 'text':'The observed count was 16 wells.'}
        write_jsonl(self.index, [self.record])
        answer = {'type':'result','sample_id':'s','question':'How many?',
                  'answer':'There were 16 biological replicates. [P02:1:p1]',
                  'provided_passage_ids':['P02:1:p1']}
        write_jsonl(self.answers, [answer])
        evidence = {key:self.record[key] for key in ('id','source_id','source_sha256','source_url','section_path','paragraph')}
        candidate = {'type':'candidate','candidate_id':'s:1','sample_id':'s','question':'How many?',
                     'candidate_text':answer['answer'],'provided_evidence':[evidence], 'citation_inspection':{}}
        meta = {'type':'metadata','answers_sha256':sha256(self.answers),'index_sha256':sha256(self.index),'candidate_count':1}
        write_jsonl(self.candidates,[meta,candidate])
        self.common = ['--candidates',str(self.candidates),'--answers',str(self.answers),'--index',str(self.index)]
        self.claim = '16 biological replicates'

    def invoke(self, args):
        with contextlib.redirect_stdout(io.StringIO()) as out, contextlib.redirect_stderr(io.StringIO()) as err:
            status = main(args)
        return status, out.getvalue(), err.getvalue()

    def record_args(self):
        return ['record']+self.common+['--reviews',str(self.reviews),'--id','s:1',
            '--claim',self.claim,'--decision','supported','--reviewer','reviewer-test',
            '--note','Test rationale','--passage-id','P02:1:p1','--quote','16 wells']

    def test_show_context_and_summary_without_creating_reviews(self):
        status, out, _ = self.invoke(['show']+self.common+['--id','s:1'])
        self.assertEqual(status,0)
        self.assertEqual(json.loads(out)['provided_evidence'][0]['text'],self.record['text'])
        status, out, _ = self.invoke(['summary']+self.common+['--reviews',str(self.reviews)])
        self.assertEqual(status,0)
        self.assertEqual(json.loads(out)['review_events'],0)
        self.assertFalse(self.reviews.exists())

    def test_export_packet_is_blank_and_never_overwrites(self):
        packet=self.root/'packet.md'
        args=['export']+self.common+['--output',str(packet)]
        self.assertEqual(self.invoke(args)[0],0)
        content=packet.read_text()
        self.assertIn('There were 16 biological replicates',content)
        self.assertIn('The observed count was 16 wells.',content)
        self.assertIn('待审核',content)
        self.assertEqual(self.invoke(args)[0],1)
        self.assertEqual(packet.read_text(),content)

    def test_missing_evidence_and_non_exact_claim_do_not_write(self):
        args=self.record_args()
        args[args.index('--quote')+1]='   '
        self.assertEqual(self.invoke(args)[0],1)
        self.assertFalse(self.reviews.exists())
        args=self.record_args()
        args[args.index('--quote')+1]='not in evidence'
        status, _, _ = self.invoke(args)
        self.assertEqual(status,1)
        self.assertFalse(self.reviews.exists())
        args=self.record_args()
        args[args.index('--claim')+1]='invented claim'
        status, _, _ = self.invoke(args)
        self.assertEqual(status,1)
        self.assertFalse(self.reviews.exists())

    def test_append_revision_and_separate_reviewer(self):
        args=self.record_args()
        status, out, _ = self.invoke(args)
        self.assertEqual(status,0)
        event=json.loads(out)
        self.assertEqual(event['evidence_quote'],'16 wells')
        self.assertIn('self-declared',event['notice'])
        before=self.reviews.read_text()
        self.assertEqual(self.invoke(args)[0],1)
        self.assertEqual(self.reviews.read_text(),before)
        revised=args+['--supersedes',event['event_id']]
        self.assertEqual(self.invoke(revised)[0],0)
        other=self.record_args()
        other[other.index('--reviewer')+1]='second-reviewer'
        self.assertEqual(self.invoke(other)[0],0)
        self.assertEqual(len(self.reviews.read_text().splitlines()),3)
        status,out,_=self.invoke(['summary']+self.common+['--reviews',str(self.reviews)])
        self.assertEqual(json.loads(out)['candidates_with_records'],1)
        self.assertIn('does not establish complete review',json.loads(out)['notice'])

    def test_withdrawal_requires_a_prior_review(self):
        args=self.record_args()
        args[args.index('--decision')+1]='withdrawn'
        self.assertEqual(self.invoke(args)[0],1)
        self.assertFalse(self.reviews.exists())
        initial=self.record_args()
        status,out,_=self.invoke(initial)
        self.assertEqual(status,0)
        withdrawal=args+['--supersedes',json.loads(out)['event_id']]
        self.assertEqual(self.invoke(withdrawal)[0],0)
        self.assertEqual(len(self.reviews.read_text().splitlines()),2)

    def test_changed_source_or_candidate_metadata_is_rejected(self):
        self.index.write_text(self.index.read_text()+'\n')
        with self.assertRaisesRegex(ValueError,'index SHA-256'):
            load_context(self.candidates,self.answers,self.index)


if __name__ == '__main__':
    unittest.main()
