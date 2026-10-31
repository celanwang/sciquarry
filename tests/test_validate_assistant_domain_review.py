import copy
import unittest

from sciquarry.validate_assistant_domain_review import validate


SAMPLE={'id':'s','evidence':[{'source_id':'P06','passage_id':'P06:2.2:p1','source_sha256':'source-hash'}]}
INDEX={'id':'P06:2.2:p1','source_id':'P06','source_sha256':'source-hash','text':'HS-5 cells were grown in DMEM.'}
META={'type':'metadata','review_kind':'assistant_preliminary_not_expert','sample_count':1,
      'sample_files':[{'path':'samples.jsonl','sha256':'sample-hash'}],
      'index_files':[{'path':'index.jsonl','sha256':'index-hash'}],
      'notice':'Assistant preliminary review only; not expert approval and not training authorization.'}
REVIEW={'type':'assistant_domain_review','sample_id':'s','reviewer_kind':'assistant',
        'review_status':'assistant_preliminary_domain_review_pending',
        'recommended_decision':'approve_for_expert_confirmation',
        'question_scope':'pass','evidence_support':'pass','conditions_and_numbers':'pass',
        'citation_alignment':'pass','risk_and_limits':'pass','rationale':'培养基与段落一致。',
        'proposed_changes':None,'risk_tags':[],'evidence_passage_ids':['P06:2.2:p1'],
        'evidence_anchors':[{'passage_id':'P06:2.2:p1','quote':'HS-5 cells were grown in DMEM'}]}


class AssistantDomainReviewValidationTest(unittest.TestCase):
    def setUp(self):
        self.meta=copy.deepcopy(META)
        self.review=copy.deepcopy(REVIEW)
        self.sample=copy.deepcopy(SAMPLE)
        self.index=copy.deepcopy(INDEX)

    def run_validation(self):
        return validate([self.meta,self.review],[self.sample],[self.index],
                        [{'path':'samples.jsonl','sha256':'sample-hash'}],
                        [{'path':'index.jsonl','sha256':'index-hash'}])

    def test_accepts_preliminary_review_with_passage_quote(self):
        result=self.run_validation()
        self.assertEqual(result['sample_count'],1)
        self.assertEqual(result['review_kind'],'assistant_preliminary_not_expert')
        self.assertIn('no clinical correctness',result['notice'])

    def test_rejects_hash_or_expert_status_changes(self):
        with self.assertRaisesRegex(ValueError,'provenance does not match'):
            validate([self.meta,self.review],[self.sample],[self.index],
                     [{'path':'samples.jsonl','sha256':'other'}],
                     [{'path':'index.jsonl','sha256':'index-hash'}])
        self.meta['review_kind']='expert_approved'
        with self.assertRaisesRegex(ValueError,'assistant preliminary'):
            self.run_validation()
        self.meta['review_kind']='assistant_preliminary_not_expert'
        self.review['reviewer_kind']='human_domain_expert'
        with self.assertRaisesRegex(ValueError,'review metadata mismatch'):
            self.run_validation()

    def test_rejects_quote_missing_from_passage_and_bare_approval(self):
        self.review['evidence_anchors'][0]['quote']='10 mM invented dose'
        with self.assertRaisesRegex(ValueError,'evidence quote not found'):
            self.run_validation()
        self.review['evidence_anchors'][0]['quote']='HS-5 cells were grown in DMEM'
        self.review['recommended_decision']='approve'
        with self.assertRaisesRegex(ValueError,'invalid recommended decision'):
            self.run_validation()

    def test_revise_requires_a_change_and_proposed_text(self):
        self.review['recommended_decision']='revise'
        self.review['conditions_and_numbers']='needs_change'
        with self.assertRaisesRegex(ValueError,'requires proposed changes'):
            self.run_validation()
        self.review['proposed_changes']='补上段落中的浓度。'
        result=self.run_validation()
        self.assertEqual(result['decisions']['revise'],1)

    def test_approval_cannot_carry_a_failing_check(self):
        self.review['conditions_and_numbers']='needs_change'
        with self.assertRaisesRegex(ValueError,'requires passing checks'):
            self.run_validation()


if __name__=='__main__':
    unittest.main()
