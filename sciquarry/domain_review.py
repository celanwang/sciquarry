"""Export and check a source-bound, blank domain review packet for QA samples.

Review decisions are self-declared; this tool cannot authenticate reviewers,
determine expertise, validate medical facts, or approve data for training.
"""
import argparse
import csv
from collections import Counter
from datetime import date, datetime, timezone
import json
from pathlib import Path
import re
import sys

from sciquarry.evaluate import prepare, read_jsonl, sha256
from sciquarry.sft import write_json

CHECKS = ('question_scope', 'evidence_support', 'conditions_and_numbers', 'citation_alignment', 'risk_and_limits')
CHECK_VALUES = ('pending', 'pass', 'needs_change', 'uncertain', 'not_applicable')
DECISIONS = ('pending', 'approve', 'revise', 'exclude')
FIELDS = ('sample_id', 'decision') + tuple('check_' + key for key in CHECKS) + ('reviewer', 'reviewer_background', 'reviewed_at', 'rationale', 'proposed_changes', 'corrected_answer', 'additional_evidence')


def render_literal(value):
    text = str(value)
    length = max([3] + [len(x) + 1 for x in re.findall(r'`+', text)])
    fence = '`' * length
    return f'{fence}text\n{text}\n{fence}\n'


def render_markdown(cases, files):
    out = ['# 领域专家问答样本审核材料（待审核）\n',
           '这是助手准备的草稿，不代表领域专家结论；引用原文受来源许可约束，分享前核对许可、署名和第三方材料。\n',
           '请逐题核查问题、证据与答案，在 reviews.csv 对应 ID 处填写判断；模板不会自动记录本文档中的文字。\n',
           '可补查文献图表及原文版本，但超出所列段落的内容应明确记录，不能默认为已提供证据。\n',
           '来源文件及索引 SHA-256：\n']
    for item in files:
        out.append(f'- `{item["name"]}`：`{item["sha256"]}`\n')
    for case in cases:
        s = case['sample']
        out.extend([f'\n## {s["id"]}\n', '\n**问题**\n', render_literal(s['question']),
                    '\n**答题范围**\n', render_literal(s.get('evidence_scope', '仅依据列出的证据。')),
                    '\n**草拟参考回答（待审核）**\n', render_literal(s['reference_answer']),
                    '\n**答案可得性**：' + str(s['answerability']) + '\n',
                    '\n**证据**\n'])
        for p in case['passages']:
            out.extend([f'\n- 段落 `{p["id"]}`；来源：{p["source_url"]}；章节：' + ' > '.join(p['section_path']) + f'；原文 SHA-256：`{p["source_sha256"]}`\n', render_literal(p['text'])])
        out.append('\n**核对**：问题与范围、证据支持、实验条件与数字、引用对应、风险与局限。\n')
    return ''.join(out)


def create_packet(sample_paths, index_paths, output):
    if not sample_paths or not index_paths: raise ValueError('sample and index files are required')
    samples = [row for path in sample_paths for row in read_jsonl(path)]
    records = [row for path in index_paths for row in read_jsonl(path)]
    by_id = prepare(samples, records)
    for sample in samples:
        for annotation in sample['evidence']:
            original = by_id[annotation['passage_id']]
            if annotation.get('url') != original['source_url']:
                raise ValueError(f"{sample['id']}: source URL does not match index")
    cases = [{'sample_id': s['id'], 'sample': s,
              'passages': [by_id[a['passage_id']] for a in s['evidence']]} for s in samples]
    if any(s.get('review', {}).get('status') != 'pending_domain_review' for s in samples):
        raise ValueError('packet must contain samples pending domain review')
    inputs = [{'name': str(p), 'sha256': sha256(p)} for p in sample_paths + index_paths]
    output.mkdir(parents=True, exist_ok=False)
    cases_file = output / 'cases.jsonl'
    with cases_file.open('x', encoding='utf-8') as f:
        for case in cases: f.write(json.dumps(case, ensure_ascii=False) + '\n')
    reviews_file = output / 'reviews.csv'
    with reviews_file.open('x', encoding='utf-8-sig', newline='') as f:
        writer = csv.DictWriter(f, fieldnames=FIELDS)
        writer.writeheader()
        for case in cases:
            review = {'sample_id': case['sample_id'], 'decision': 'pending',
                      **{'check_' + k: 'pending' for k in CHECKS}}
            writer.writerow(review)
    (output / 'packet.md').write_text(render_markdown(cases, inputs), encoding='utf-8')
    manifest = {'schema': 1, 'created_at': datetime.now(timezone.utc).isoformat(), 'inputs': inputs,
                'cases_sha256': sha256(cases_file), 'packet_sha256': sha256(output / 'packet.md'),
                'count': len(cases), 'purpose': 'domain_review_only_not_training_approval',
                'notice': 'Reviewers and conclusions are self-declared and not authenticated.'}
    write_json(output / 'manifest.json', manifest)
    return manifest


def nonempty(value):
    return isinstance(value, str) and bool(value.strip())


def check_packet(packet):
    manifest = json.loads((packet / 'manifest.json').read_text(encoding='utf-8'))
    if manifest.get('schema') != 1 or manifest.get('purpose') != 'domain_review_only_not_training_approval':
        raise ValueError('invalid review packet manifest')
    if sha256(packet / 'cases.jsonl') != manifest['cases_sha256'] or sha256(packet / 'packet.md') != manifest['packet_sha256']:
        raise ValueError('packet content changed; create a new packet for changed cases')
    cases = read_jsonl(packet / 'cases.jsonl')
    with (packet / 'reviews.csv').open(encoding='utf-8-sig', newline='') as f:
        reader = csv.DictReader(f)
        if tuple(reader.fieldnames or ()) != FIELDS: raise ValueError('invalid review sheet columns')
        reviews = list(reader)
    ids = [c['sample_id'] for c in cases]
    if len(ids) != manifest['count'] or len(set(ids)) != len(ids): raise ValueError('invalid case IDs')
    by_id = {r.get('sample_id'): r for r in reviews}
    if len(reviews) != len(by_id) or set(by_id) != set(ids): raise ValueError('review IDs do not match packet cases')
    counts = Counter()
    for rid in ids:
        r = by_id[rid]; decision = r.get('decision'); checks = {k: r.get('check_' + k) for k in CHECKS}
        if decision not in DECISIONS or any(v not in CHECK_VALUES for v in checks.values()):
            raise ValueError(f'{rid}: invalid decision or checklist')
        if decision == 'pending':
            if any(r.get(k) for k in ('reviewer', 'reviewer_background', 'reviewed_at', 'rationale', 'proposed_changes', 'corrected_answer', 'additional_evidence')) or any(v != 'pending' for v in checks.values()):
                raise ValueError(f'{rid}: unfinished record must remain blank until decision is recorded')
        else:
            if any(not nonempty(r.get(k)) for k in ('reviewer', 'reviewer_background', 'reviewed_at', 'rationale')):
                raise ValueError(f'{rid}: reviewer, background, date and rationale are required')
            try:
                if not re.fullmatch(r'\d{4}-\d{2}-\d{2}', r['reviewed_at']): raise ValueError('invalid date')
                date.fromisoformat(r['reviewed_at'])
            except ValueError: raise ValueError(f'{rid}: reviewed_at must be an ISO date') from None
            if any(v == 'pending' for v in checks.values()): raise ValueError(f'{rid}: complete every checklist item')
            if decision == 'approve' and any(v not in ('pass', 'not_applicable') for v in checks.values()):
                raise ValueError(f'{rid}: approval conflicts with checklist')
            if decision == 'revise' and not (nonempty(r.get('corrected_answer')) or nonempty(r.get('proposed_changes'))):
                raise ValueError(f'{rid}: revision requires proposed changes or a corrected answer')
        counts[decision] += 1
    return {'count': len(ids), 'decisions': {key: counts[key] for key in DECISIONS},
            'cases_sha256': manifest['cases_sha256'], 'reviews_sha256': sha256(packet / 'reviews.csv'),
            'notice': 'Counts do not validate expertise, medical correctness or training suitability.'}


def main(argv=None):
    p = argparse.ArgumentParser(description=__doc__); sub = p.add_subparsers(dest='cmd', required=True)
    export = sub.add_parser('export'); export.add_argument('--samples', type=Path, action='append', required=True); export.add_argument('--index', type=Path, action='append', required=True); export.add_argument('--output', type=Path, required=True)
    check = sub.add_parser('check'); check.add_argument('--packet', type=Path, required=True)
    args = p.parse_args(argv)
    try:
        result = create_packet(args.samples, args.index, args.output) if args.cmd == 'export' else check_packet(args.packet)
        print(json.dumps(result, ensure_ascii=False, indent=2))
    except (OSError, ValueError, KeyError, TypeError, json.JSONDecodeError) as exc:
        print(f'Error: {exc}', file=sys.stderr); return 1
    return 0


if __name__ == '__main__': sys.exit(main())
