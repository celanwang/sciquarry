import unittest

from sciquarry.claim_review import candidates_for_result, split_candidates


class ClaimReviewTest(unittest.TestCase):
    def test_citations_after_full_stop_stay_with_preceding_segment(self):
        text='第一项事实。[P02:1.1:p1] 第二项事实 [P02:1.1:p1]。'
        result=split_candidates(text)
        self.assertEqual(result,['第一项事实。[P02:1.1:p1]','第二项事实 [P02:1.1:p1]。'])

    def test_candidate_is_unreviewed_and_only_uses_given_sources(self):
        records={'P02:1:p1':{'id':'P02:1:p1','source_id':'P02','source_url':'https://example.com',
                              'source_sha256':'abc','section_path':['Results'],'paragraph':1},
                 'P02:1:p2':{'id':'P02:1:p2','source_id':'P02','source_url':'https://example.com',
                              'source_sha256':'abc','section_path':['Results'],'paragraph':2}}
        result={'sample_id':'sample-1','question':'test','answer':'一个事实。[P02:1:p1] 另一个事实。',
                'provided_passage_ids':['P02:1:p1']}
        rows=candidates_for_result(result,records)
        self.assertEqual(len(rows),2)
        self.assertEqual(rows[0]['review']['status'],'pending')
        self.assertIsNone(rows[0]['review']['decision'])
        self.assertEqual([p['id'] for p in rows[0]['provided_evidence']],['P02:1:p1'])
        self.assertEqual(rows[0]['citation_inspection']['valid_citations'],['P02:1:p1'])
        self.assertEqual(rows[1]['citation_inspection']['citation_status'],'missing')

    def test_missing_passage_fails(self):
        with self.assertRaisesRegex(ValueError,'evidence missing'):
            candidates_for_result({'sample_id':'s','provided_passage_ids':['missing']},{})


if __name__=='__main__':
    unittest.main()
