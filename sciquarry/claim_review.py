"""Prepare human review candidates from evidence-bound model responses.

Segmentation is only a convenience: a candidate may be a heading, contain
several assertions, or lack context. This module does not verify facts.
"""

import argparse
from datetime import datetime, timezone
import json
from pathlib import Path
import re
import sys

from sciquarry.ask import inspect_citations
from sciquarry.evaluate import read_jsonl, sha256


def split_candidates(answer):
    # Keep bracketed citations after a sentence with that sentence. Do not split
    # at ASCII periods: they occur in passage IDs, measurements and abbreviations.
    pattern = r"[^\n。！？!?]+[。！？!?]?(?:\s*\[[^\[\]\n]+\])*"
    return [match.group(0).strip() for match in re.finditer(pattern, answer) if match.group(0).strip()]


def candidates_for_result(result, by_id):
    evidence_ids = result['provided_passage_ids']
    if not evidence_ids or any(pid not in by_id for pid in evidence_ids):
        raise ValueError(f"{result['sample_id']}: evidence missing from index")
    evidence = [{'id':pid,'source_id':by_id[pid]['source_id'],'source_url':by_id[pid]['source_url'],
                 'source_sha256':by_id[pid]['source_sha256'],'section_path':by_id[pid]['section_path'],
                 'paragraph':by_id[pid]['paragraph']} for pid in evidence_ids]
    candidates = split_candidates(result['answer'])
    if not candidates:
        raise ValueError(f"{result['sample_id']}: empty answer")
    rows=[]
    for n, text in enumerate(candidates, 1):
        citations=inspect_citations(text,set(evidence_ids))
        rows.append({'type':'candidate','candidate_id':f"{result['sample_id']}:{n}",
                     'sample_id':result['sample_id'], 'question':result['question'],
                     'candidate_text':text, 'provided_evidence':evidence,
                     'citation_inspection':citations,
                     'review':{'status':'pending','atomic_claim':None,'decision':None,
                               'supporting_passage_id':None,'supporting_location':None,
                               'reviewer':None,'reviewed_at':None,'notes':None}})
    return rows


def main(argv=None):
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--answers',type=Path,required=True)
    parser.add_argument('--index',type=Path,required=True)
    parser.add_argument('--output',type=Path,required=True)
    args=parser.parse_args(argv)
    try:
        answer_rows=read_jsonl(args.answers)
        if not answer_rows or answer_rows[0].get('type')!='metadata' or answer_rows[0].get('mode')!='answer':
            raise ValueError('answers must be an answer-evaluation JSONL')
        if answer_rows[-1].get('type')!='summary' or answer_rows[-1].get('failures'):
            raise ValueError('answer evaluation must be complete without failed samples')
        if sha256(args.index)!=answer_rows[0].get('index_sha256'):
            raise ValueError('index hash does not match the original evaluation')
        records=read_jsonl(args.index)
        by_id={r['id']:r for r in records}
        if len(by_id)!=len(records):
            raise ValueError('duplicate passage IDs')
        result_rows=[r for r in answer_rows if r.get('type')=='result']
        if len(result_rows)!=answer_rows[0]['sample_count'] or len({r['sample_id'] for r in result_rows})!=len(result_rows):
            raise ValueError('answer evaluation has missing or duplicate results')
        candidates=[candidate for row in result_rows for candidate in candidates_for_result(row,by_id)]
        args.output.parent.mkdir(parents=True,exist_ok=True)
        with args.output.open('x',encoding='utf-8') as out:
            meta={'type':'metadata','created_at':datetime.now(timezone.utc).isoformat(),
                  'answers_path':str(args.answers),'answers_sha256':sha256(args.answers),
                  'index_path':str(args.index),'index_sha256':sha256(args.index),
                  'code_sha256':sha256(Path('sciquarry/claim_review.py')),
                  'sample_count':len(result_rows),'candidate_count':len(candidates),
                  'notice':'Candidate segments only; not atomic claims, expert reviews, or factual verdicts.'}
            for row in [meta]+candidates:
                out.write(json.dumps(row,ensure_ascii=False)+'\n')
        print(json.dumps({'samples':len(result_rows),'candidate_segments':len(candidates),'all_reviews_pending':True}))
        return 0
    except (OSError, ValueError, KeyError, TypeError, json.JSONDecodeError) as exc:
        print(f'Error: {exc}',file=sys.stderr)
        return 1


if __name__=='__main__':
    sys.exit(main())
