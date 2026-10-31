"""Validate provenance and offsets of assistant-preliminary review records.

This is a structural audit only: it does not evaluate medical correctness,
prove that a source supports a finding, or replace domain review.
"""

import argparse
from collections import Counter
import json
from pathlib import Path
import sys

from sciquarry.evaluate import read_jsonl, sha256

DECISIONS={'supported','contradicted','insufficient_evidence','out_of_scope','needs_clarification','not_a_claim'}


def _check_range(span, text, label):
    start,end=span['start'],span['end']
    if type(start) is not int or type(end) is not int or not 0<=start<end<=len(text):
        raise ValueError(f'{label}: invalid Unicode character offsets')


def validate(review_rows,candidate_rows,index_rows,candidates_hash,index_hash):
    if not review_rows or review_rows[0].get('type')!='metadata':
        raise ValueError('review file must begin with metadata')
    meta=review_rows[0]
    if meta.get('review_kind')!='assistant_preliminary_not_expert':
        raise ValueError('review must be explicitly marked as assistant preliminary')
    if meta.get('candidates_sha256')!=candidates_hash or meta.get('index_sha256')!=index_hash:
        raise ValueError('review provenance does not match input files')
    candidates={x['candidate_id']:x for x in candidate_rows if x.get('type')=='candidate'}
    if len(candidates)!=sum(x.get('type')=='candidate' for x in candidate_rows):
        raise ValueError('duplicate candidate IDs')
    index={x['id']:x for x in index_rows}
    if len(index)!=len(index_rows):
        raise ValueError('duplicate passage IDs')
    rows=review_rows[1:]
    if len(rows)!=meta.get('candidate_count') or len(rows)!=len(candidates):
        raise ValueError('review does not cover all candidates exactly once')
    seen=set(); findings_seen=set(); counts=Counter()
    for row in rows:
        cid=row['candidate_id']
        if cid in seen or cid not in candidates:
            raise ValueError(f'duplicate or unknown candidate: {cid}')
        seen.add(cid); candidate=candidates[cid]
        if (row.get('reviewer_kind')!='assistant' or
            row.get('review_status')!='assistant_preliminary_domain_review_pending' or
            row.get('sample_id')!=candidate['sample_id'] or
            row.get('citation_inspection')!=candidate['citation_inspection']):
            raise ValueError(f'{cid}: review metadata mismatch')
        evidence_ids=[e['id'] for e in candidate['provided_evidence']]
        for entry in candidate['provided_evidence']:
            original=index.get(entry['id'])
            if original is None or entry['source_sha256']!=original['source_sha256'] or entry['source_id']!=original['source_id']:
                raise ValueError(f'{cid}: candidate evidence provenance mismatch')
        if not row.get('findings'):
            raise ValueError(f'{cid}: no findings')
        for f in row['findings']:
            fid=f['finding_id']
            if fid in findings_seen or not fid.startswith(cid+'#'):
                raise ValueError(f'{fid}: duplicate or mismatched finding ID')
            findings_seen.add(fid)
            _check_range(f['claim_span'],candidate['candidate_text'],fid)
            if f['decision'] not in DECISIONS or not f['rationale'].strip():
                raise ValueError(f'{fid}: invalid decision or empty rationale')
            if f['evidence_scope_ids']!=evidence_ids:
                raise ValueError(f'{fid}: evidence scope mismatch')
            if not isinstance(f['risk_tags'],list) or any(not isinstance(x,str) or not x for x in f['risk_tags']):
                raise ValueError(f'{fid}: invalid risk tags')
            for e in f['evidence_spans']:
                pid=e['passage_id']
                if pid not in evidence_ids or pid not in index or e['source_sha256']!=index[pid]['source_sha256']:
                    raise ValueError(f'{fid}: evidence source mismatch')
                _check_range(e,index[pid]['text'],fid)
            counts[f['decision']]+=1
    return {'candidate_count':len(rows),'finding_count':len(findings_seen),
            'decisions':dict(counts),'review_kind':'assistant_preliminary_not_expert',
            'notice':'Structure only; no clinical correctness or expert review is established.'}


def main(argv=None):
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--reviews',type=Path,required=True)
    parser.add_argument('--candidates',type=Path,required=True)
    parser.add_argument('--index',type=Path,required=True)
    args=parser.parse_args(argv)
    try:
        result=validate(read_jsonl(args.reviews),read_jsonl(args.candidates),read_jsonl(args.index),
                        sha256(args.candidates),sha256(args.index))
        print(json.dumps(result,ensure_ascii=False,indent=2))
        return 0
    except (OSError,ValueError,KeyError,TypeError,json.JSONDecodeError) as exc:
        print(f'Error: {exc}',file=sys.stderr)
        return 1


if __name__=='__main__':
    sys.exit(main())
