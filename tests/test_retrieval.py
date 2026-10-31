import tempfile
import unittest
from pathlib import Path

from sciquarry.retrieval import index_article, search


ARTICLE = b'''<article><front><article-meta>
<article-id pub-id-type="pmcid">PMC123</article-id>
</article-meta></front><body><sec id="results"><title>Results</title>
<sec id="study"><title>Cell study</title>
<p>Imatinib affected <italic>BCR</italic>-Abl cells after 72 hours.</p>
<p>Another paragraph.</p></sec></sec></body></article>'''


class RetrievalTest(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.path = Path(self.temp.name) / "article.xml"
        self.path.write_bytes(ARTICLE)
        self.addCleanup(self.temp.cleanup)

    def test_index_provenance_and_location(self):
        rows = index_article(self.path, "P99", "PMC123", "https://example.org/article")
        self.assertEqual(len(rows), 2)
        self.assertEqual(rows[0]["id"], "P99:1.1:p1")
        self.assertEqual(rows[0]["section_path"], ["Results", "Cell study"])
        self.assertEqual(rows[0]["section_id"], "study")
        self.assertIn("BCR-Abl", rows[0]["text"])
        self.assertEqual(len(rows[0]["source_sha256"]), 64)
        self.assertEqual(rows, index_article(self.path, "P99", "PMC123", "https://example.org/article"))

    def test_wrong_article_is_rejected(self):
        with self.assertRaisesRegex(ValueError, "PMCID"):
            index_article(self.path, "P99", "PMC999", "https://example.org/article")

    def test_search_ranks_evidence_and_no_match_is_empty(self):
        rows = index_article(self.path, "P99", "PMC123", "https://example.org/article")
        self.assertEqual(search(rows, "imatinib cells 72")[0]["id"], "P99:1.1:p1")
        self.assertEqual(search(rows, "伊马替尼")[0]["id"], "P99:1.1:p1")
        self.assertEqual(search(rows, "未知概念"), [])
        self.assertEqual(search(rows, ""), [])
        with self.assertRaises(ValueError):
            search(rows, "cells", 0)


if __name__ == "__main__":
    unittest.main()
