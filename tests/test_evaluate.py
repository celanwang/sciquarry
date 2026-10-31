import unittest
from unittest.mock import patch

from sciquarry.evaluate import answer_result, prepare, retrieval_result


RECORDS = [
    {"id": "P02:1:p1", "source_id": "P02", "source_sha256": "aaa", "section_path": ["Results"], "text": "imatinib cells"},
    {"id": "P02:1:p2", "source_id": "P02", "source_sha256": "aaa", "section_path": ["Methods"], "text": "differentiation assay"},
    {"id": "P02:1:p3", "source_id": "P02", "source_sha256": "aaa", "section_path": ["Other"], "text": "imatinib unrelated"},
]
SAMPLE = {"id": "dev-1", "question": "imatinib cells", "answerability": "answerable",
          "evidence": [{"passage_id": "P02:1:p1", "source_id": "P02", "source_sha256": "aaa"},
                       {"passage_id": "P02:1:p2", "source_id": "P02", "source_sha256": "aaa"}]}


class EvaluationTest(unittest.TestCase):
    def test_fails_when_evidence_missing_or_from_another_revision(self):
        with self.assertRaisesRegex(ValueError, "missing passage"):
            prepare([SAMPLE], RECORDS[:1])
        altered = [dict(x) for x in RECORDS]
        altered[0]["source_sha256"] = "changed"
        with self.assertRaisesRegex(ValueError, "provenance mismatch"):
            prepare([SAMPLE], altered)

    def test_retrieval_distinguishes_any_from_all(self):
        result = retrieval_result(SAMPLE, RECORDS, top_k=1)
        self.assertTrue(result["any_hit"])
        self.assertFalse(result["all_hit"])
        self.assertEqual(result["expected_passage_ids"], ["P02:1:p1", "P02:1:p2"])

    def test_answer_sends_only_annotated_evidence(self):
        expected = {"answer": "answer", "citation_status": "missing", "unknown_citations": [], "finish_reason": "stop"}
        with patch("sciquarry.evaluate.answer_with_evidence", return_value=expected) as call:
            result = answer_result(SAMPLE, prepare([SAMPLE], RECORDS), "model", "http://localhost:8080/v1", True)
        actual = call.call_args.args[0]
        self.assertEqual([x["id"] for x in actual], ["P02:1:p1", "P02:1:p2"])
        self.assertEqual(result["review"]["status"], "pending_human_review")


if __name__ == "__main__":
    unittest.main()
