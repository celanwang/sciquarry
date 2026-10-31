"""Validate structure and provenance of assistant-preliminary domain reviews.

This is a structural audit only: it does not evaluate medical correctness,
prove that a passage supports a conclusion, or replace domain-expert review.
"""

import argparse
from collections import Counter
import json
from pathlib import Path
import sys

from sciquarry.evaluate import read_jsonl, sha256

DECISIONS={'approve_for_expert_confirmation','revise','exclude','uncertain'}
CHECK_FIELDS=('question_scope','evidence_support','conditions_and_numbers','citation_alignment','risk_and_limits')
CHECK_VALUES={'pass','needs_change','uncertain','not_applicable'}
REVIEW_STATUS='assistant_preliminary_domain_review_pending'


def _listed(paths):
    rows=[]; hashes=[]
    for path in paths:
        rows.extend(read_jsonl(path))
        hashes.append({'path':path.as_posix(),'sha256':sha256(path)})
    return rows, hashes


def _match_hashes(declared, actual, label):
    if not isinstance(declared, list) or len(declared)!=len(actual):
        raise ValueError(f'{label}: provenance file list mismatch')
    for item, expected in zip(declared, actual):
        if not isinstance(item, dict) or item.get('path')!=expected['path'] or item.get('sha256')!=expected['sha256']:
            raise ValueError(f'{label}: provenance does not match input files')


def validate(review_rows, sample_rows, index_rows, sample_hashes, index_hashes):
    if not review_rows or review_rows[0].get('type')!='metadata':
        raise ValueError('review file must begin with metadata')
    meta=review_rows[0]
    if meta.get('review_kind')!='assistant_preliminary_not_expert':
        raise ValueError('review must be explicitly marked as assistant preliminary')
    if 'not expert approval' not in (meta.get('notice') or '').lower():
        raise ValueError('metadata notice must state this is not expert approval')
    _match_hashes(meta.get('sample_files'), sample_hashes, 'samples')
    _match_hashes(meta.get('index_files'), index_hashes, 'indexes')
    samples={}
    for sample in sample_rows:
        sid=sample['id']
        if sid in samples:
            raise ValueError(f'duplicate sample ID: {sid}')
        samples[sid]=sample
    index={}
    for passage in index_rows:
        pid=passage['id']
        if pid in index:
            raise ValueError(f'duplicate passage ID: {pid}')
        index[pid]=passage
    rows=review_rows[1:]
    if len(rows)!=meta.get('sample_count') or len(rows)!=len(samples):
        raise ValueError('review does not cover all samples exactly once')
    seen=set(); counts=Counter()
    for row in rows:
        sid=row.get('sample_id')
        if row.get('type')!='assistant_domain_review' or sid in seen or sid not in samples:
            raise ValueError(f'duplicate or unknown sample: {sid}')
        seen.add(sid)
        if (row.get('reviewer_kind')!='assistant' or
            row.get('review_status')!=REVIEW_STATUS):
            raise ValueError(f'{sid}: review metadata mismatch')
        decision=row.get('recommended_decision')
        if decision not in DECISIONS:
            raise ValueError(f'{sid}: invalid recommended decision')
        checks=[]
        for field in CHECK_FIELDS:
            value=row.get(field)
            if value not in CHECK_VALUES:
                raise ValueError(f'{sid}: invalid {field}')
            checks.append(value)
        if decision=='approve_for_expert_confirmation' and any(v not in {'pass','not_applicable'} for v in checks):
            raise ValueError(f'{sid}: approval recommendation requires passing checks')
        if decision=='revise' and not any(v in {'needs_change','uncertain'} for v in checks):
            raise ValueError(f'{sid}: revise recommendation needs a failing or uncertain check')
        if decision=='uncertain' and 'uncertain' not in checks:
            raise ValueError(f'{sid}: uncertain recommendation needs an uncertain check')
        rationale=(row.get('rationale') or '').strip()
        if not rationale:
            raise ValueError(f'{sid}: empty rationale')
        if 'not_applicable' in checks and '不适用' not in rationale:
            raise ValueError(f'{sid}: not_applicable check must be explained')
        changes=row.get('proposed_changes')
        if decision=='revise':
            if not isinstance(changes, str) or not changes.strip():
                raise ValueError(f'{sid}: revise recommendation requires proposed changes')
        elif decision=='approve_for_expert_confirmation' and changes not in (None, ''):
            raise ValueError(f'{sid}: approval recommendation cannot include proposed changes')
        tags=row.get('risk_tags')
        if not isinstance(tags, list) or any(not isinstance(tag, str) or not tag for tag in tags):
            raise ValueError(f'{sid}: invalid risk tags')
        expected=[item['passage_id'] for item in samples[sid]['evidence']]
        if row.get('evidence_passage_ids')!=expected:
            raise ValueError(f'{sid}: evidence passage list mismatch')
        anchors=row.get('evidence_anchors')
        if not isinstance(anchors, list) or not anchors:
            raise ValueError(f'{sid}: evidence anchors required')
        covered=set()
        for anchor in anchors:
            pid=anchor.get('passage_id'); quote=anchor.get('quote')
            if pid not in expected or pid not in index:
                raise ValueError(f'{sid}: anchor passage is outside the sample evidence')
            passage=index[pid]
            source=next(item for item in samples[sid]['evidence'] if item['passage_id']==pid)
            if (source.get('source_sha256')!=passage.get('source_sha256') or
                source.get('source_id')!=passage.get('source_id')):
                raise ValueError(f'{sid}: evidence source mismatch')
            if not isinstance(quote, str) or not quote or quote not in passage['text']:
                raise ValueError(f'{sid}: evidence quote not found in passage {pid}')
            covered.add(pid)
        if covered!=set(expected):
            raise ValueError(f'{sid}: each evidence passage needs a quote anchor')
        counts[decision]+=1
    if seen!=set(samples):
        raise ValueError('review does not cover all samples exactly once')
    return {'sample_count':len(rows),'decisions':dict(counts),
            'review_kind':'assistant_preliminary_not_expert',
            'notice':'Structure only; no clinical correctness or expert review is established.'}


def main(argv=None):
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--reviews',type=Path,required=True)
    parser.add_argument('--samples',type=Path,action='append',required=True)
    parser.add_argument('--index',type=Path,action='append',required=True)
    args=parser.parse_args(argv)
    try:
        samples,sample_hashes=_listed(args.samples)
        indexes,index_hashes=_listed(args.index)
        result=validate(read_jsonl(args.reviews),samples,indexes,sample_hashes,index_hashes)
        print(json.dumps(result,ensure_ascii=False,indent=2))
        return 0
    except (OSError,ValueError,KeyError,TypeError,json.JSONDecodeError) as exc:
        print(f'Error: {exc}',file=sys.stderr)
        return 1


if __name__=='__main__':
    sys.exit(main())
