"""Create reviewable before/after comparisons for curated development cases.

The program compares inputs and output metadata; it never decides whether a
medical claim is correct. All case checklists require human review.
"""

import argparse
from datetime import datetime, timezone
import json
from pathlib import Path
import sys

from sciquarry.evaluate import read_jsonl, sha256


def load_answer_run(path):
    rows=read_jsonl(path)
    if not rows or rows[0].get('type')!='metadata' or rows[0].get('mode')!='answer':
        raise ValueError('input must be an answer-evaluation run')
    if rows[-1].get('type')!='summary' or rows[-1].get('failures'):
        raise ValueError('answer run is incomplete or contains failures')
    records=[r for r in rows if r.get('type')=='result']
    by_id={r['sample_id']:r for r in records}
    if (len(records)!=rows[0].get('sample_count') or len(by_id)!=len(records)
            or rows[-1].get('successes')!=len(records)):
        raise ValueError('answer run has missing or duplicate results')
    return rows[0],by_id


def compare(cases, samples, reviews, before_meta, before, after_meta, after):
    if not cases or cases[0].get('type')!='metadata':
        raise ValueError('regression cases must start with metadata')
    case_rows=cases[1:]
    by_sample={s['id']:s for s in samples}
    if len(by_sample)!=len(samples):
        raise ValueError('duplicate sample IDs')
    if not reviews or reviews[0].get('review_kind')!='assistant_preliminary_not_expert':
        raise ValueError('reviews must be assistant-preliminary records')
    if any(r.get('reviewer_kind')!='assistant' or r.get('review_status')!='assistant_preliminary_domain_review_pending' for r in reviews[1:]):
        raise ValueError('review records must remain pending domain review')
    findings={f['finding_id']:r['sample_id'] for r in reviews[1:] for f in r['findings']}
    if len(findings)!=sum(len(r['findings']) for r in reviews[1:]):
        raise ValueError('duplicate finding IDs')
    for key in ('sample_sha256','index_sha256','model','base_url','no_thinking','temperature','max_tokens'):
        if before_meta.get(key)!=after_meta.get(key):
            raise ValueError(f'answer run configuration mismatch: {key}')
    if before_meta.get('sample_sha256')!=cases[0].get('samples_sha256'):
        raise ValueError('answer runs use different samples from the regression cases')
    seen_cases=set(); seen_samples=set(); rows=[]
    for case in case_rows:
        cid=case['id']; sid=case['sample_id']
        if case.get('type')!='case' or cid in seen_cases or sid in seen_samples or sid not in by_sample:
            raise ValueError(f'duplicate or invalid regression case: {cid}')
        seen_cases.add(cid); seen_samples.add(sid)
        if case.get('review_status')!='assistant_preliminary_domain_review_pending':
            raise ValueError(f'{cid}: case must remain pending domain review')
        if not case['finding_ids'] or any(findings.get(fid)!=sid for fid in case['finding_ids']):
            raise ValueError(f'{cid}: finding IDs do not match sample')
        if not case['checks_for_human_review']:
            raise ValueError(f'{cid}: missing review checklist')
        s=by_sample[sid]; expected=[e['passage_id'] for e in s['evidence']]
        if case['evidence_ids']!=expected:
            raise ValueError(f'{cid}: case evidence differs from sample')
        if sid not in before or sid not in after:
            raise ValueError(f'{cid}: missing answer')
        a,b=before[sid],after[sid]
        if any(x.get('question')!=s['question'] or x.get('provided_passage_ids')!=expected for x in (a,b)):
            raise ValueError(f'{cid}: answer question or evidence differs')
        if any(not isinstance(x.get('answer'),str) or not x['answer'].strip() for x in (a,b)):
            raise ValueError(f'{cid}: answer is empty or invalid')
        if a.get('system_fingerprint') and b.get('system_fingerprint') and a['system_fingerprint']!=b['system_fingerprint']:
            raise ValueError(f'{cid}: model service fingerprint changed')
        rows.append({'type':'case_comparison','case_id':cid,'sample_id':sid,'question':s['question'],
                     'evidence_ids':expected,'finding_ids':case['finding_ids'],
                     'checks_for_human_review':case['checks_for_human_review'],
                     'before':{k:a.get(k) for k in ('answer','citation_status','unknown_citations','malformed_citations','review_flags','finish_reason','system_fingerprint')},
                     'after':{k:b.get(k) for k in ('answer','citation_status','unknown_citations','malformed_citations','review_flags','finish_reason','system_fingerprint')},
                     'text_identical':a.get('answer')==b.get('answer'),
                     'service_fingerprint_verified':bool(a.get('system_fingerprint') and b.get('system_fingerprint')),
                     'comparison_status':'pending_manual_review',
                     'reviewer':None,'reviewed_at':None,'verdict':None})
    if not rows:
        raise ValueError('no regression cases')
    return rows


def main(argv=None):
    p=argparse.ArgumentParser(description=__doc__)
    for name in ('cases','samples','reviews','before','after','index','output'):
        p.add_argument('--'+name,type=Path,required=True)
    args=p.parse_args(argv)
    try:
        cases=read_jsonl(args.cases); samples=read_jsonl(args.samples); reviews=read_jsonl(args.reviews)
        if not cases or cases[0].get('samples_sha256')!=sha256(args.samples) or cases[0].get('assistant_review_sha256')!=sha256(args.reviews):
            raise ValueError('case manifest does not match samples or assistant review')
        if cases[0].get('baseline_answer_sha256')!=sha256(args.before):
            raise ValueError('before run does not match the case baseline')
        a_meta,a=load_answer_run(args.before); b_meta,b=load_answer_run(args.after)
        if a_meta.get('index_sha256')!=sha256(args.index) or b_meta.get('index_sha256')!=sha256(args.index):
            raise ValueError('answer runs do not match the supplied evidence index')
        rows=compare(cases,samples,reviews,a_meta,a,b_meta,b)
        meta={'type':'metadata','created_at':datetime.now(timezone.utc).isoformat(),
              'cases_sha256':sha256(args.cases),'samples_sha256':sha256(args.samples),
              'assistant_review_sha256':sha256(args.reviews),'index_sha256':sha256(args.index),
              'before_sha256':sha256(args.before),'after_sha256':sha256(args.after),
              'comparison_code_sha256':sha256(Path('sciquarry/regression.py')),
              'case_count':len(rows),'before_code_sha256':a_meta.get('code_sha256'),
              'after_code_sha256':b_meta.get('code_sha256'),
              'notice':'Development comparison only; all semantic verdicts pending manual review.'}
        args.output.parent.mkdir(parents=True,exist_ok=True)
        with args.output.open('x',encoding='utf-8') as f:
            for row in [meta]+rows:
                f.write(json.dumps(row,ensure_ascii=False)+'\n')
        print(json.dumps({'cases':len(rows),'pending_manual_review':len(rows),
                          'text_identical':sum(r['text_identical'] for r in rows)},ensure_ascii=False))
        return 0
    except (OSError,ValueError,KeyError,TypeError,json.JSONDecodeError) as exc:
        print(f'Error: {exc}',file=sys.stderr)
        return 1


if __name__=='__main__':
    sys.exit(main())
