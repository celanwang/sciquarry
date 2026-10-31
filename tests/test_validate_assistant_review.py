import copy
import unittest

from sciquarry.validate_assistant_review import validate


CANDIDATE={'type':'candidate','candidate_id':'s:1','sample_id':'s',
           'candidate_text':'甲细胞改变。','citation_inspection':{'citation_status':'recognized'},
           'provided_evidence':[{'id':'P02:1:p1','source_id':'P02','source_sha256':'source-hash'}]}
INDEX={'id':'P02:1:p1','source_id':'P02','source_sha256':'source-hash','text':'原文证据。'}
META={'type':'metadata','review_kind':'assistant_preliminary_not_expert','candidate_count':1,
      'candidates_sha256':'candidate-hash','index_sha256':'index-hash'}
REVIEW={'type':'assistant_review','candidate_id':'s:1','sample_id':'s',
        'reviewer_kind':'assistant','review_status':'assistant_preliminary_domain_review_pending',
        'citation_inspection':{'citation_status':'recognized'},
        'findings':[{'finding_id':'s:1#1','claim_span':{'start':0,'end':3},'decision':'supported',
                     'evidence_scope_ids':['P02:1:p1'],'risk_tags':[],'rationale':'Test rationale',
                     'evidence_spans':[{'passage_id':'P02:1:p1','source_sha256':'source-hash','start':0,'end':2}]}]}


class AssistantReviewValidationTest(unittest.TestCase):
    def setUp(self):
        self.meta=copy.deepcopy(META)
        self.review=copy.deepcopy(REVIEW)
        self.candidate=copy.deepcopy(CANDIDATE)
        self.index=copy.deepcopy(INDEX)

    def run_validation(self):
        return validate([self.meta,self.review],[self.candidate],[self.index],'candidate-hash','index-hash')

    def test_unicode_offsets_and_review_remains_preliminary(self):
        result=self.run_validation()
        self.assertEqual((result['candidate_count'],result['finding_count']),(1,1))
        self.assertEqual(result['review_kind'],'assistant_preliminary_not_expert')
        self.assertIn('no clinical correctness',result['notice'])

    def test_rejects_source_or_snapshot_mismatch(self):
        self.index['source_sha256']='changed'
        with self.assertRaisesRegex(ValueError,'candidate evidence provenance mismatch'):
            self.run_validation()
        with self.assertRaisesRegex(ValueError,'provenance does not match'):
            validate([self.meta,self.review],[self.candidate],[self.index],'other-hash','index-hash')

    def test_rejects_invalid_offsets_and_claimed_expert_status(self):
        self.review['findings'][0]['claim_span']['end']=999
        with self.assertRaisesRegex(ValueError,'invalid Unicode'):
            self.run_validation()
        self.review['findings'][0]['claim_span']['end']=3
        self.review['reviewer_kind']='expert'
        with self.assertRaisesRegex(ValueError,'review metadata mismatch'):
            self.run_validation()

    def test_rejects_finding_bound_to_wrong_candidate(self):
        self.review['findings'][0]['finding_id']='other:1#1'
        with self.assertRaisesRegex(ValueError,'mismatched finding ID'):
            self.run_validation()

    def test_rejects_missing_findings(self):
        self.review['findings']=[]
        with self.assertRaisesRegex(ValueError,'no findings'):
            self.run_validation()


if __name__=='__main__':
    unittest.main()
