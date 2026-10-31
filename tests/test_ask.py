import json
import threading
import unittest
from http.server import BaseHTTPRequestHandler, HTTPServer
from unittest.mock import patch

from sciquarry.ask import answer_question, inspect_citations, local_chat_url, review_flags


RECORDS = [{"id": "P02:1.1:p1", "section_path": ["Results"],
            "text": "Imatinib treated BCR Abl cells for 72 hours.",
            "source_id": "P02", "source_url": "https://example.org/article"}]


class FakeHandler(BaseHTTPRequestHandler):
    requests = []
    answer = "细胞经伊马替尼处理 72 小时。[P02:1.1:p1]"

    def do_POST(self):
        body = self.rfile.read(int(self.headers["Content-Length"]))
        self.requests.append((self.path, json.loads(body)))
        payload = json.dumps({"choices": [{"message": {"content": self.answer}, "finish_reason": "stop"}]}).encode()
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.end_headers()
        self.wfile.write(payload)

    def log_message(self, *args):
        pass


class AskTest(unittest.TestCase):
    def setUp(self):
        FakeHandler.requests = []
        FakeHandler.answer = "细胞经伊马替尼处理 72 小时。[P02:1.1:p1]"
        self.server = HTTPServer(("127.0.0.1", 0), FakeHandler)
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        self.thread.start()
        self.url = f"http://127.0.0.1:{self.server.server_port}/v1"

    def tearDown(self):
        self.server.shutdown()
        self.thread.join()
        self.server.server_close()

    def test_sends_only_retrieved_evidence_and_returns_source(self):
        result = answer_question(RECORDS, "伊马替尼处理细胞多久？", "test-model", self.url)
        self.assertEqual(result["citation_status"], "recognized")
        self.assertEqual(result["finish_reason"], "stop")
        self.assertEqual(result["sources"][0]["id"], "P02:1.1:p1")
        path, request = FakeHandler.requests[0]
        self.assertEqual(path, "/v1/chat/completions")
        self.assertEqual(request["model"], "test-model")
        self.assertIn("[P02:1.1:p1] Imatinib", request["messages"][1]["content"])

    def test_no_thinking_is_explicitly_opt_in(self):
        answer_question(RECORDS, "伊马替尼", "test-model", self.url, no_thinking=True)
        self.assertEqual(FakeHandler.requests[0][1]["chat_template_kwargs"], {"enable_thinking": False})

    def test_unknown_and_missing_citations_are_flagged(self):
        FakeHandler.answer = "结果。[ P02:9:p9 ]"
        result = answer_question(RECORDS, "伊马替尼", "test-model", self.url)
        self.assertEqual(result["citation_status"], "unknown_citation")
        self.assertEqual(result["unknown_citations"], ["P02:9:p9"])
        FakeHandler.answer = "结果没有引用。"
        self.assertEqual(answer_question(RECORDS, "伊马替尼", "test-model", self.url)["citation_status"], "missing")

    def test_mixed_valid_and_malformed_citation_is_not_recognized(self):
        result = inspect_citations("结论 [P02:1.1:p1]，另见 [1.1:p2]。", {"P02:1.1:p1"})
        self.assertEqual(result["citation_status"], "malformed_citation")
        self.assertEqual(result["valid_citations"], ["P02:1.1:p1"])
        self.assertEqual(result["malformed_citations"], ["1.1:p2"])
        unknown = inspect_citations("结论 [P02:8:p3]。", {"P02:1.1:p1"})
        self.assertEqual(unknown["citation_status"], "unknown_citation")
        self.assertEqual(inspect_citations("见 [1]。", set())["citation_status"], "missing")

    def test_numeric_biological_replicates_require_review(self):
        self.assertEqual(review_flags("共进行了16次独立生物学重复。"), ["verify_biological_replicate_count"])
        self.assertEqual(review_flags("There were 3 independent biological replicates."), ["verify_biological_replicate_count"])
        self.assertEqual(review_flags("片段没有说明独立生物学重复次数。"), [])

    def test_no_evidence_does_not_call_model(self):
        with patch("sciquarry.ask.build_opener") as opener:
            result = answer_question(RECORDS, "未知概念", "test-model", self.url)
        self.assertEqual(result["citation_status"], "no_evidence")
        opener.assert_not_called()

    def test_rejects_external_and_credential_urls(self):
        for url in ("https://example.com/v1", "http://127.0.0.1@example.com/v1", "http://localhost/v1?x=1"):
            with self.subTest(url=url), self.assertRaises(ValueError):
                local_chat_url(url)


if __name__ == "__main__":
    unittest.main()
