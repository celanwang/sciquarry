"""Inspect candidate claims and append attributable human review records.

This tool validates provenance and exact source locations, not expertise or
whether a review verdict is scientifically correct.
"""

import argparse
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import re
import sys
import uuid

from sciquarry.evaluate import read_jsonl, sha256

DECISIONS = ('supported', 'contradicted', 'insufficient_evidence', 'out_of_scope', 'not_a_claim', 'withdrawn')


def load_context(candidates_path, answers_path, index_path):
    candidates = read_jsonl(candidates_path)
    if not candidates or candidates[0].get('type') != 'metadata':
        raise ValueError('candidate file must begin with metadata')
    meta = candidates[0]
    if sha256(answers_path) != meta.get('answers_sha256'):
        raise ValueError('answer file SHA-256 does not match candidates')
    if sha256(index_path) != meta.get('index_sha256'):
        raise ValueError('index SHA-256 does not match candidates')
    candidate_rows = candidates[1:]
    if (any(x.get('type') != 'candidate' for x in candidate_rows)
            or len(candidate_rows) != meta.get('candidate_count')):
        raise ValueError('candidate file has missing or invalid records')
    by_candidate = {x['candidate_id']: x for x in candidate_rows}
    if len(by_candidate) != len(candidate_rows):
        raise ValueError('candidate IDs are not unique')
    index_rows = read_jsonl(index_path)
    by_passage = {x['id']: x for x in index_rows}
    if len(by_passage) != len(index_rows):
        raise ValueError('index passage IDs are not unique')
    answer_rows = read_jsonl(answers_path)
    results = [x for x in answer_rows if x.get('type') == 'result']
    by_answer = {x['sample_id']: x for x in results}
    if len(by_answer) != len(results):
        raise ValueError('answer sample IDs are not unique')
    for candidate in candidate_rows:
        answer = by_answer.get(candidate['sample_id'])
        if (answer is None or candidate['question'] != answer['question']
                or candidate['candidate_text'] not in answer['answer']):
            raise ValueError(f"candidate {candidate['candidate_id']} does not match original answer")
        evidence = candidate['provided_evidence']
        if [x['id'] for x in evidence] != answer['provided_passage_ids']:
            raise ValueError(f"candidate {candidate['candidate_id']} has a mismatched evidence scope")
        for entry in evidence:
            original = by_passage.get(entry['id'])
            if original is None or any(entry[k] != original[k] for k in ('source_id', 'source_sha256', 'source_url', 'section_path', 'paragraph')):
                raise ValueError(f"candidate {candidate['candidate_id']} has mismatched source metadata")
    return by_candidate, by_answer, by_passage


def inspect_candidate(candidate_id, context):
    candidates, answers, passages = context
    if candidate_id not in candidates:
        raise ValueError(f'unknown candidate ID: {candidate_id}')
    candidate = candidates[candidate_id]
    return {'candidate_id': candidate_id, 'question': candidate['question'],
            'full_answer': answers[candidate['sample_id']]['answer'],
            'candidate_text': candidate['candidate_text'],
            'citation_inspection': candidate['citation_inspection'],
            'provided_evidence': [passages[x['id']] for x in candidate['provided_evidence']]}


def load_events(path, candidates_hash, index_hash, candidates):
    events = read_jsonl(path) if path.exists() else []
    ids = set()
    for event in events:
        if event.get('type') != 'human_review' or event.get('event_id') in ids:
            raise ValueError('review log has an invalid or duplicate event')
        ids.add(event['event_id'])
        if (event.get('candidates_sha256') != candidates_hash or event.get('index_sha256') != index_hash
                or event.get('candidate_id') not in candidates):
            raise ValueError('review log belongs to a different candidate or index version')
    return events


def create_event(candidate_id, claim, decision, reviewer, note, passage_id, quote,
                 supersedes, context, events, candidates_hash, index_hash):
    candidates, _, passages = context
    if candidate_id not in candidates:
        raise ValueError(f'unknown candidate ID: {candidate_id}')
    candidate = candidates[candidate_id]
    if not claim.strip() or claim not in candidate['candidate_text']:
        raise ValueError('claim must be a non-empty exact substring of the candidate text')
    if decision not in DECISIONS or not reviewer.strip() or not note.strip():
        raise ValueError('a valid decision, non-empty reviewer and rationale are required')
    if (passage_id is not None and not passage_id.strip()) or (quote is not None and not quote.strip()):
        raise ValueError('passage ID and evidence quote cannot be blank')
    if bool(passage_id) != bool(quote):
        raise ValueError('passage ID and exact quote must be supplied together')
    if decision == 'withdrawn' and not supersedes:
        raise ValueError('withdrawn requires --supersedes with the active event ID')
    if decision in ('supported', 'contradicted') and not passage_id:
        raise ValueError('supported or contradicted requires a passage ID and exact evidence quote')
    allowed = {x['id'] for x in candidate['provided_evidence']}
    if passage_id and (passage_id not in allowed or quote not in passages[passage_id]['text']):
        raise ValueError('evidence must be an exact quote from a passage provided to the model')
    previous = [x for x in events if x['candidate_id'] == candidate_id
                and x['claim'] == claim and x['reviewer'] == reviewer]
    superseded_ids = {x.get('supersedes') for x in previous if x.get('supersedes')}
    active = [x for x in previous if x['event_id'] not in superseded_ids]
    if active:
        if len(active) != 1 or supersedes != active[0]['event_id']:
            raise ValueError('an existing review by this reviewer requires --supersedes with its current event ID')
    elif supersedes:
        raise ValueError('supersedes must reference an existing active review by the same reviewer')
    return {'type':'human_review', 'event_id':str(uuid.uuid4()),
            'recorded_at':datetime.now(timezone.utc).isoformat(),
            'candidates_sha256':candidates_hash, 'index_sha256':index_hash,
            'candidate_id':candidate_id, 'claim':claim, 'decision':decision,
            'evidence_passage_id':passage_id, 'evidence_quote':quote, 'reviewer':reviewer,
            'rationale':note, 'supersedes':supersedes,
            'notice':'Reviewer identity and expertise are self-declared; verdict is not automatically verified.'}


def render_packet(context, candidates_hash, answers_hash, index_hash):
    """Render a blank, source-linked packet; it never imports review verdicts."""
    candidates, answers, passages = context

    def literal(text):
        runs = [len(x) for x in re.findall(r"`+", text)]
        fence = "`" * max(3, (max(runs) + 1) if runs else 3)
        return f"{fence}text\n{text}\n{fence}\n"

    lines = ["# 事实断言审核材料（空白快照）\n",
             "该文件不包含审核结论，也不显示后续审核记录；每个候选片段可能含多个断言，须人工拆分。\n",
             "原文受来源许可约束，分享前请核对对应文献的许可、署名及第三方材料。\n",
             f"候选文件 SHA-256: `{candidates_hash}`  \n回答文件 SHA-256: `{answers_hash}`  \n索引 SHA-256: `{index_hash}`\n"]
    grouped = {}
    for candidate in candidates.values():
        grouped.setdefault(candidate['sample_id'], []).append(candidate)
    for sample_id, group in grouped.items():
        answer = answers[sample_id]
        lines.extend([f"## {sample_id}\n", "### 问题\n", literal(answer['question']),
                      "### 完整模型回答\n", literal(answer['answer']), "### 提供给模型的证据\n"])
        for pid in answer['provided_passage_ids']:
            p = passages[pid]
            lines.extend([f"**{pid}** — {p['source_url']}  \n来源文件 SHA-256: `{p['source_sha256']}`\n",
                          literal(p['text'])])
        lines.append("### 待审候选片段\n")
        for candidate in group:
            lines.extend([f"**{candidate['candidate_id']}**（待审核）\n", literal(candidate['candidate_text']),
                          "断言 / 证据位置 / 判断与理由 / 审核人 / 日期：待填写\n"])
    return "\n".join(lines)


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest='command', required=True)
    for name in ('show', 'record', 'summary', 'export'):
        p = sub.add_parser(name)
        p.add_argument('--candidates', type=Path, required=True)
        p.add_argument('--answers', type=Path, required=True)
        p.add_argument('--index', type=Path, required=True)
        if name in ('record', 'summary'):
            p.add_argument('--reviews', type=Path, required=True)
        if name in ('show', 'record'):
            p.add_argument('--id', required=True)
        if name == 'export':
            p.add_argument('--output', type=Path, required=True)
        if name == 'record':
            p.add_argument('--claim', required=True)
            p.add_argument('--decision', choices=DECISIONS, required=True)
            p.add_argument('--reviewer', required=True)
            p.add_argument('--note', required=True)
            p.add_argument('--passage-id')
            p.add_argument('--quote')
            p.add_argument('--supersedes')
    args = parser.parse_args(argv)
    try:
        context = load_context(args.candidates, args.answers, args.index)
        if args.command == 'show':
            print(json.dumps(inspect_candidate(args.id, context), ensure_ascii=False, indent=2))
            return 0
        if args.command == 'export':
            packet = render_packet(context, sha256(args.candidates), sha256(args.answers), sha256(args.index))
            args.output.parent.mkdir(parents=True, exist_ok=True)
            with args.output.open('x', encoding='utf-8') as output:
                output.write(packet)
            print(json.dumps({'output':str(args.output), 'candidates':len(context[0]), 'status':'blank_snapshot'}))
            return 0
        candidates_hash, index_hash = sha256(args.candidates), sha256(args.index)
        events = load_events(args.reviews, candidates_hash, index_hash, context[0])
        if args.command == 'summary':
            touched = {e['candidate_id'] for e in events}
            print(json.dumps({'candidates':len(context[0]), 'review_events':len(events),
                              'candidates_with_records':len(touched),
                              'candidates_without_records':len(context[0])-len(touched),
                              'notice':'A record does not establish complete review or reviewer expertise.'},
                             ensure_ascii=False, indent=2))
            return 0
        event = create_event(args.id, args.claim, args.decision, args.reviewer, args.note,
                             args.passage_id, args.quote, args.supersedes, context, events,
                             candidates_hash, index_hash)
        args.reviews.parent.mkdir(parents=True, exist_ok=True)
        payload = (json.dumps(event, ensure_ascii=False) + '\n').encode('utf-8')
        fd = os.open(args.reviews, os.O_WRONLY | os.O_CREAT | os.O_APPEND, 0o600)
        try:
            if os.write(fd, payload) != len(payload):
                raise OSError('incomplete write to review log')
        finally:
            os.close(fd)
        print(json.dumps(event, ensure_ascii=False, indent=2))
        return 0
    except (OSError, ValueError, KeyError, TypeError, json.JSONDecodeError) as exc:
        print(f'Error: {exc}', file=sys.stderr)
        return 1


if __name__ == '__main__':
    sys.exit(main())
