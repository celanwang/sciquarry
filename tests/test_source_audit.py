import csv
import json
from pathlib import Path
import tempfile
import unittest

from sciquarry.evaluate import sha256
from sciquarry.source_audit import audit, is_identifier_in_text, write_review_sheet


class SourceAuditTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(); self.root = Path(self.tmp.name)
        self.catalog = self.root / 'catalog.json'
        self.entries = []
        self.add_source('A', 'PMC123', '10.1000/a', '101', 'Alice', 'Wong', 'GSE123', '10.1000/b GSE999')
        self.add_source('B', 'PMC456', '10.1000/b', '202', 'Alice', 'Wong', 'GSE123', 'GSE999')
        self.entries.append({'id':'C', 'pmcid':'PMC789'})
        self.write_catalog()

    def tearDown(self): self.tmp.cleanup()

    def write_catalog(self): self.catalog.write_text(json.dumps({'sources': self.entries}))

    def add_source(self, sid, pmcid, doi, pmid, given, family, body, refs):
        path = self.root / (sid + '.xml')
        path.write_text(f'''<article><front><article-meta><article-id pub-id-type="pmcid">{pmcid}</article-id><article-id pub-id-type="doi">{doi}</article-id><contrib-group><contrib contrib-type="author"><name><surname>{family}</surname><given-names>{given}</given-names></name></contrib></contrib-group></article-meta></front><body><sec><p>{body}</p></sec></body><back><ref-list><ref>{refs}</ref></ref-list></back></article>''')
        self.entries.append({'id':sid,'pmcid':pmcid,'pmid':pmid,'doi':doi,'url':'https://example.org',
                             'local_asset':{'raw_path':str(path),'source_sha256':sha256(path)}})

    def test_detects_source_signals_but_not_reference_only_accessions(self):
        result=audit(self.catalog)
        self.assertEqual(len(result['skipped']),1)
        pair=result['pairs'][0]
        self.assertEqual(pair['direct_citation_identifiers'],[{'from':'A','to':'B','matched_identifier_types':['doi']}])
        self.assertEqual(pair['same_exact_normalized_author_names'],['alice wong'])
        self.assertEqual(pair['shared_accession_mentions_outside_reference_lists'],['GSE123'])
        self.assertEqual(pair['manual_relationship_review'],'pending')
        self.assertNotIn('GSE999',pair['shared_accession_mentions_outside_reference_lists'])

    def test_changed_file_fails_and_doi_mismatch_fails(self):
        path=Path(self.entries[0]['local_asset']['raw_path']); path.write_text(path.read_text()+'\n')
        with self.assertRaisesRegex(ValueError,'SHA-256'): audit(self.catalog)
        self.entries[0]['local_asset']['source_sha256']=sha256(path)
        self.entries[0]['doi']='10.1000/wrong'; self.write_catalog()
        with self.assertRaisesRegex(ValueError,'DOI mismatch'): audit(self.catalog)

    def test_review_sheet_is_blank_and_does_not_overwrite(self):
        path = self.root / 'review.csv'
        write_review_sheet(audit(self.catalog), path)
        with path.open(encoding='utf-8-sig', newline='') as f:
            rows = list(csv.DictReader(f))
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]['status'], 'pending')
        self.assertEqual(rows[0]['reviewer'], '')
        with self.assertRaises(FileExistsError): write_review_sheet(audit(self.catalog), path)

    def test_identifiers_require_boundaries(self):
        self.assertTrue(is_identifier_in_text('101', 'PMID 101;'))
        self.assertFalse(is_identifier_in_text('101', 'PMID 101123'))
        self.assertFalse(is_identifier_in_text(None, 'anything'))


if __name__ == '__main__': unittest.main()
