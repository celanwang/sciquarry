"""Report traceable JATS relationship signals without deciding independence."""
import argparse
import csv
from datetime import datetime, timezone
import itertools
import json
from pathlib import Path
import re
import sys
import xml.etree.ElementTree as ET

from sciquarry.evaluate import sha256
from sciquarry.sft import write_json

ACCESSION = re.compile(r'\b(?:GSE\d+|GSM\d+|PRJNA\d+|PRJEB\d+|SRP\d+|SRR\d+|ERP\d+|ERR\d+|E-MTAB-\d+)\b', re.IGNORECASE)


def flattened(node):
    return ' '.join(''.join(node.itertext()).split()) if node is not None else ''


def author_names(meta):
    result = []
    for contrib in meta.findall('./contrib-group/contrib'):
        if contrib.get('contrib-type') not in (None, 'author'): continue
        name = contrib.find('name')
        if name is not None:
            given = (name.findtext('given-names') or '').strip()
            family = (name.findtext('surname') or '').strip()
            if given and family: result.append(' '.join((given + ' ' + family).casefold().split()))
    return sorted(set(result))


def load_source(entry):
    asset = entry.get('local_asset')
    if not asset or not asset.get('raw_path'):
        return None
    path = Path(asset['raw_path'])
    if not path.is_file(): return None
    digest = sha256(path)
    if digest != asset.get('source_sha256'):
        raise ValueError(f"{entry['id']}: source file SHA-256 does not match catalog")
    root = ET.parse(path).getroot()
    meta = root.find('./front/article-meta')
    if meta is None: raise ValueError(f"{entry['id']}: missing JATS article metadata")
    pmcids = {('PMC' + (x.text or '').strip().removeprefix('PMC')).upper()
              for x in meta.findall('article-id') if x.get('pub-id-type') in ('pmc', 'pmcid')}
    if entry['pmcid'].upper() not in pmcids: raise ValueError(f"{entry['id']}: PMCID mismatch")
    actual_dois = {(x.text or '').strip().casefold() for x in meta.findall('article-id') if x.get('pub-id-type') == 'doi'}
    if entry.get('doi') and entry['doi'].casefold() not in actual_dois:
        raise ValueError(f"{entry['id']}: DOI mismatch")
    refs = ' '.join(flattened(ref) for ref in root.findall('.//ref-list//ref'))
    # Article body/back matter may mention datasets belonging to earlier studies.
    # Exclude reference lists but never assume a mentioned accession is owned by the article.
    for parent in root.iter():
        for child in list(parent):
            if child.tag.rsplit('}', 1)[-1] == 'ref-list': parent.remove(child)
    outside_refs = flattened(root.find('./body')) + ' ' + flattened(root.find('./back')) + ' ' + flattened(meta)
    return {'id': entry['id'], 'pmcid': entry['pmcid'], 'doi': entry.get('doi'),
            'pmid': entry.get('pmid'), 'url': entry.get('url'), 'model_note': entry.get('model'), 'source_path': str(path),
            'source_sha256': digest, 'authors': author_names(meta),
            'accessions_mentioned_outside_reference_list': sorted({x.upper() for x in ACCESSION.findall(outside_refs)}),
            '_references': refs}


def is_identifier_in_text(identifier, text):
    if not identifier: return False
    return bool(re.search(r'(?<![a-zA-Z0-9])' + re.escape(identifier) + r'(?![a-zA-Z0-9])', text, re.IGNORECASE))


def audit(catalog_path):
    catalog = json.loads(catalog_path.read_text(encoding='utf-8'))
    entries = catalog['sources']; ids = [e['id'] for e in entries]
    if len(set(ids)) != len(ids): raise ValueError('catalog has duplicate source IDs')
    available, skipped = [], []
    for entry in entries:
        item = load_source(entry)
        if item is None: skipped.append({'id': entry['id'], 'reason': 'no local raw JATS XML in catalog or file missing'})
        else: available.append(item)
    if len(available) < 2: raise ValueError('at least two local source files are required')
    pairs = []
    for a, b in itertools.combinations(available, 2):
        citations = []
        for source, target in ((a, b), (b, a)):
            matches = [key for key in ('doi', 'pmid', 'pmcid') if is_identifier_in_text(target.get(key), source['_references'])]
            if matches: citations.append({'from': source['id'], 'to': target['id'], 'matched_identifier_types': matches})
        authors = sorted(set(a['authors']).intersection(b['authors']))
        accessions = sorted(set(a['accessions_mentioned_outside_reference_list']).intersection(b['accessions_mentioned_outside_reference_list']))
        pairs.append({'source_ids': [a['id'], b['id']], 'direct_citation_identifiers': citations,
                      'same_exact_normalized_author_names': authors, 'shared_accession_mentions_outside_reference_lists': accessions,
                      'manual_relationship_review': 'pending'})
    for a in available: del a['_references']
    return {'schema': 1, 'created_at': datetime.now(timezone.utc).isoformat(),
            'catalog_path': str(catalog_path), 'catalog_sha256': sha256(catalog_path),
            'sources': available, 'skipped': skipped, 'pairs': pairs,
            'limitations': ['Literal identifier and exact full-name matches are incomplete.',
                            'Shared accession mentions do not establish ownership or shared experiments.',
                            'No match does not establish research independence.',
                            'Cell lineage, methods, supplements, people, data reuse and source rights require human review.']}



def write_review_sheet(result, output):
    fields = ('source_a', 'source_b', 'source_a_model', 'source_b_model',
              'citation_signals', 'shared_author_signals', 'shared_accession_mentions',
              'status', 'reviewer', 'reviewer_background', 'reviewed_at', 'rationale', 'evidence_links')
    sources = {s['id']: s for s in result['sources']}
    with output.open('x', encoding='utf-8-sig', newline='') as f:
        writer = csv.DictWriter(f, fieldnames=fields); writer.writeheader()
        for pair in result['pairs']:
            a, b = pair['source_ids']
            writer.writerow({'source_a': a, 'source_b': b,
                             'source_a_model': sources[a].get('model_note'),
                             'source_b_model': sources[b].get('model_note'),
                             'citation_signals': json.dumps(pair['direct_citation_identifiers'], ensure_ascii=False),
                             'shared_author_signals': '; '.join(pair['same_exact_normalized_author_names']),
                             'shared_accession_mentions': '; '.join(pair['shared_accession_mentions_outside_reference_lists']),
                             'status': 'pending'})

def main(argv=None):
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--catalog', type=Path, required=True); p.add_argument('--output', type=Path, required=True)
    p.add_argument('--review-sheet', type=Path)
    args = p.parse_args(argv)
    try:
        result = audit(args.catalog)
        if args.output.exists() or (args.review_sheet and args.review_sheet.exists()): raise ValueError('output already exists')
        write_json(args.output, result)
        if args.review_sheet: write_review_sheet(result, args.review_sheet)
        print(json.dumps({'sources': len(result['sources']), 'pairs': len(result['pairs']), 'skipped': result['skipped'], 'output': str(args.output)}, ensure_ascii=False, indent=2))
    except (OSError, KeyError, TypeError, ValueError, ET.ParseError, json.JSONDecodeError) as e:
        print(f'Error: {e}', file=sys.stderr); return 1
    return 0


if __name__ == '__main__': sys.exit(main())
