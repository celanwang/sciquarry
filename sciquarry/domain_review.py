"""Export and check a source-bound, blank domain review packet for QA samples.

Review decisions are self-declared; this tool cannot authenticate reviewers,
determine expertise, validate medical facts, or approve data for training.
"""
import argparse
import csv
from collections import Counter
from datetime import date, datetime, timezone
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
from pathlib import Path
import re
import sys
from urllib.parse import urlparse

from sciquarry.evaluate import prepare, read_jsonl, sha256
from sciquarry.sft import write_json

CHECKS = ('question_scope', 'evidence_support', 'conditions_and_numbers', 'citation_alignment', 'risk_and_limits')
CHECK_VALUES = ('pending', 'pass', 'needs_change', 'uncertain', 'not_applicable')
DECISIONS = ('pending', 'approve', 'revise', 'exclude')
FIELDS = ('sample_id', 'decision') + tuple('check_' + key for key in CHECKS) + (
    'reviewer', 'reviewer_background', 'reviewed_at', 'rationale', 'proposed_changes',
    'corrected_answer', 'additional_evidence')
FORM_TEMPLATE = Path(__file__).with_name('expert_review_form.html')


def render_literal(value):
    text = str(value)
    length = max([3] + [len(x) + 1 for x in re.findall(r'`+', text)])
    fence = '`' * length
    return f'{fence}text\n{text}\n{fence}\n'


def render_markdown(cases, files):
    out = ['# 领域专家问答样本审核材料（待审核）\n',
           '这是助手准备的草稿，不代表领域专家结论；引用原文受来源许可约束，分享前核对许可、署名和第三方材料。\n',
           '请逐题核查问题、证据与答案，在 reviews.csv 或 review-form.html / 本机 serve 中对应 ID 处填写判断；模板不会自动记录本文档中的文字。\n',
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


def blank_review(sample_id):
    row = {'sample_id': sample_id, 'decision': 'pending'}
    for key in CHECKS:
        row['check_' + key] = 'pending'
    for key in ('reviewer', 'reviewer_background', 'reviewed_at', 'rationale',
                'proposed_changes', 'corrected_answer', 'additional_evidence'):
        row[key] = ''
    return row


def nonempty(value):
    return isinstance(value, str) and bool(value.strip())


def normalize_review(row):
    out = blank_review(str(row.get('sample_id') or ''))
    for key in FIELDS:
        value = row.get(key, out.get(key, ''))
        out[key] = '' if value is None else str(value)
    return out


def validate_review_row(row):
    row = normalize_review(row)
    rid = row['sample_id'] or '(missing id)'
    decision = row['decision']
    checks = {k: row['check_' + k] for k in CHECKS}
    if decision not in DECISIONS or any(v not in CHECK_VALUES for v in checks.values()):
        raise ValueError(f'{rid}: invalid decision or checklist')
    if decision == 'pending':
        extras = ('reviewer', 'reviewer_background', 'reviewed_at', 'rationale',
                  'proposed_changes', 'corrected_answer', 'additional_evidence')
        if any(nonempty(row.get(k)) for k in extras) or any(v != 'pending' for v in checks.values()):
            raise ValueError(f'{rid}: unfinished record must remain blank until decision is recorded')
    else:
        if any(not nonempty(row.get(k)) for k in ('reviewer', 'reviewer_background', 'reviewed_at', 'rationale')):
            raise ValueError(f'{rid}: reviewer, background, date and rationale are required')
        try:
            if not re.fullmatch(r'\d{4}-\d{2}-\d{2}', row['reviewed_at']):
                raise ValueError('invalid date')
            date.fromisoformat(row['reviewed_at'])
        except ValueError as exc:
            raise ValueError(f'{rid}: reviewed_at must be an ISO date') from exc
        if any(v == 'pending' for v in checks.values()):
            raise ValueError(f'{rid}: complete every checklist item')
        if decision == 'approve' and any(v not in ('pass', 'not_applicable') for v in checks.values()):
            raise ValueError(f'{rid}: approval conflicts with checklist')
        if decision == 'revise' and not (nonempty(row.get('corrected_answer')) or nonempty(row.get('proposed_changes'))):
            raise ValueError(f'{rid}: revision requires proposed changes or a corrected answer')
    return row


def read_reviews(path):
    with path.open(encoding='utf-8-sig', newline='') as f:
        reader = csv.DictReader(f)
        if tuple(reader.fieldnames or ()) != FIELDS:
            raise ValueError('invalid review sheet columns')
        return [normalize_review(row) for row in reader]


def write_reviews(path, reviews):
    with path.open('w', encoding='utf-8-sig', newline='') as f:
        writer = csv.DictWriter(f, fieldnames=FIELDS)
        writer.writeheader()
        for row in reviews:
            writer.writerow(normalize_review(row))


def form_cases(cases):
    payload = []
    for case in cases:
        sample = case['sample']
        payload.append({
            'sample_id': case['sample_id'],
            'question': sample.get('question', ''),
            'evidence_scope': sample.get('evidence_scope', '仅依据列出的证据。'),
            'reference_answer': sample.get('reference_answer', ''),
            'answerability': sample.get('answerability', ''),
            'passages': [{
                'id': passage['id'],
                'source_url': passage.get('source_url', ''),
                'section_path': passage.get('section_path', []),
                'text': passage.get('text', ''),
            } for passage in case['passages']],
        })
    return payload


def load_packet_cases(packet):
    return read_jsonl(packet / 'cases.jsonl')


def build_form_payload(packet, live=False):
    cases = load_packet_cases(packet)
    reviews = read_reviews(packet / 'reviews.csv')
    manifest = json.loads((packet / 'manifest.json').read_text(encoding='utf-8'))
    return {
        'live': bool(live),
        'meta': {
            'packet_name': packet.name,
            'count': len(cases),
            'cases_sha256': manifest.get('cases_sha256'),
            'notice': 'Reviewers and conclusions are self-declared and not authenticated.',
        },
        'cases': form_cases(cases),
        'reviews': reviews,
    }


def render_form_html(payload):
    template = FORM_TEMPLATE.read_text(encoding='utf-8')
    marker = '/*__SCIQUARRY_PAYLOAD__*/null'
    if marker not in template:
        raise ValueError('expert review form template is missing payload marker')
    encoded = json.dumps(payload, ensure_ascii=False).replace('</', '<\\/')
    return template.replace(marker, encoded, 1)


def write_review_form(packet, live=False):
    html = render_form_html(build_form_payload(packet, live=live))
    path = packet / 'review-form.html'
    path.write_text(html, encoding='utf-8')
    return path


def create_packet(sample_paths, index_paths, output):
    if not sample_paths or not index_paths:
        raise ValueError('sample and index files are required')
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
        for case in cases:
            f.write(json.dumps(case, ensure_ascii=False) + '\n')
    reviews = [blank_review(case['sample_id']) for case in cases]
    write_reviews(output / 'reviews.csv', reviews)
    (output / 'packet.md').write_text(render_markdown(cases, inputs), encoding='utf-8')
    manifest = {'schema': 1, 'created_at': datetime.now(timezone.utc).isoformat(), 'inputs': inputs,
                'cases_sha256': sha256(cases_file), 'packet_sha256': sha256(output / 'packet.md'),
                'count': len(cases), 'purpose': 'domain_review_only_not_training_approval',
                'notice': 'Reviewers and conclusions are self-declared and not authenticated.'}
    write_json(output / 'manifest.json', manifest)
    write_review_form(output, live=False)
    return manifest


def check_packet(packet):
    manifest = json.loads((packet / 'manifest.json').read_text(encoding='utf-8'))
    if manifest.get('schema') != 1 or manifest.get('purpose') != 'domain_review_only_not_training_approval':
        raise ValueError('invalid review packet manifest')
    if sha256(packet / 'cases.jsonl') != manifest['cases_sha256'] or sha256(packet / 'packet.md') != manifest['packet_sha256']:
        raise ValueError('packet content changed; create a new packet for changed cases')
    cases = load_packet_cases(packet)
    reviews = read_reviews(packet / 'reviews.csv')
    ids = [c['sample_id'] for c in cases]
    if len(ids) != manifest['count'] or len(set(ids)) != len(ids):
        raise ValueError('invalid case IDs')
    by_id = {r['sample_id']: r for r in reviews}
    if len(reviews) != len(by_id) or set(by_id) != set(ids):
        raise ValueError('review IDs do not match packet cases')
    counts = Counter()
    for rid in ids:
        validate_review_row(by_id[rid])
        counts[by_id[rid]['decision']] += 1
    return {'count': len(ids), 'decisions': {key: counts[key] for key in DECISIONS},
            'cases_sha256': manifest['cases_sha256'], 'reviews_sha256': sha256(packet / 'reviews.csv'),
            'notice': 'Counts do not validate expertise, medical correctness or training suitability.'}


def save_review_row(packet, row):
    cases = load_packet_cases(packet)
    ids = [c['sample_id'] for c in cases]
    reviews = read_reviews(packet / 'reviews.csv')
    by_id = {r['sample_id']: r for r in reviews}
    if set(by_id) != set(ids):
        raise ValueError('review IDs do not match packet cases')
    updated = validate_review_row(row)
    if updated['sample_id'] not in by_id:
        raise ValueError(f"{updated['sample_id']}: unknown sample_id")
    by_id[updated['sample_id']] = updated
    ordered = [by_id[sample_id] for sample_id in ids]
    for item in ordered:
        validate_review_row(item)
    write_reviews(packet / 'reviews.csv', ordered)
    counts = Counter(item['decision'] for item in ordered)
    return {'sample_id': updated['sample_id'], 'decision': updated['decision'],
            'decisions': {key: counts[key] for key in DECISIONS},
            'reviews_sha256': sha256(packet / 'reviews.csv'),
            'notice': 'Saved self-declared review only; not training approval.'}


def make_form_handler(packet):
    packet = packet.resolve()

    class Handler(BaseHTTPRequestHandler):
        def _send(self, code, body, content_type):
            data = body if isinstance(body, bytes) else body.encode('utf-8')
            self.send_response(code)
            self.send_header('Content-Type', content_type)
            self.send_header('Content-Length', str(len(data)))
            self.send_header('Cache-Control', 'no-store')
            self.end_headers()
            self.wfile.write(data)

        def _json(self, code, payload):
            self._send(code, json.dumps(payload, ensure_ascii=False), 'application/json; charset=utf-8')

        def do_GET(self):
            path = urlparse(self.path).path
            try:
                if path in ('/', '/review-form.html'):
                    html = render_form_html(build_form_payload(packet, live=True))
                    self._send(200, html, 'text/html; charset=utf-8')
                elif path == '/api/state':
                    self._json(200, build_form_payload(packet, live=True))
                elif path == '/api/check':
                    self._json(200, check_packet(packet))
                else:
                    self._json(404, {'error': 'not found'})
            except (OSError, ValueError, KeyError, TypeError, json.JSONDecodeError) as exc:
                self._json(400, {'error': str(exc)})

        def do_POST(self):
            path = urlparse(self.path).path
            length = int(self.headers.get('Content-Length', '0'))
            raw = self.rfile.read(length) if length else b'{}'
            try:
                payload = json.loads(raw.decode('utf-8'))
                if path == '/api/review':
                    self._json(200, save_review_row(packet, payload.get('review') or payload))
                else:
                    self._json(404, {'error': 'not found'})
            except (OSError, ValueError, KeyError, TypeError, json.JSONDecodeError) as exc:
                self._json(400, {'error': str(exc)})

        def log_message(self, fmt, *args):
            sys.stderr.write("%s - %s\n" % (self.address_string(), fmt % args))

    return Handler


def serve_packet(packet, host='127.0.0.1', port=8765):
    packet = packet.resolve()
    if not (packet / 'manifest.json').exists():
        raise ValueError('packet directory is missing manifest.json')
    check_packet(packet)
    write_review_form(packet, live=False)
    server = ThreadingHTTPServer((host, port), make_form_handler(packet))
    print(json.dumps({
        'packet': str(packet),
        'url': f'http://{host}:{port}/',
        'notice': 'Local expert form only; no authentication or training approval.',
    }, ensure_ascii=False, indent=2))
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print('\nStopped.', file=sys.stderr)
    finally:
        server.server_close()
    return 0


def main(argv=None):
    p = argparse.ArgumentParser(description=__doc__)
    sub = p.add_subparsers(dest='cmd', required=True)
    export = sub.add_parser('export')
    export.add_argument('--samples', type=Path, action='append', required=True)
    export.add_argument('--index', type=Path, action='append', required=True)
    export.add_argument('--output', type=Path, required=True)
    check = sub.add_parser('check')
    check.add_argument('--packet', type=Path, required=True)
    form = sub.add_parser('form', help='write or refresh review-form.html inside a packet')
    form.add_argument('--packet', type=Path, required=True)
    serve = sub.add_parser('serve', help='local browser form that writes reviews.csv')
    serve.add_argument('--packet', type=Path, required=True)
    serve.add_argument('--host', default='127.0.0.1')
    serve.add_argument('--port', type=int, default=8765)
    args = p.parse_args(argv)
    try:
        if args.cmd == 'export':
            result = create_packet(args.samples, args.index, args.output)
        elif args.cmd == 'check':
            result = check_packet(args.packet)
        elif args.cmd == 'form':
            path = write_review_form(args.packet, live=False)
            result = {'form': str(path), 'reviews_sha256': sha256(args.packet / 'reviews.csv'),
                      'notice': 'Offline form downloads CSV; use serve to write reviews.csv directly.'}
        else:
            return serve_packet(args.packet, host=args.host, port=args.port)
        print(json.dumps(result, ensure_ascii=False, indent=2))
    except (OSError, ValueError, KeyError, TypeError, json.JSONDecodeError) as exc:
        print(f'Error: {exc}', file=sys.stderr)
        return 1
    return 0


if __name__ == '__main__':
    sys.exit(main())
