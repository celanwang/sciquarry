"""Prepare review-gated evidence QA data and run a reproducible MLX LoRA experiment."""
import argparse
from datetime import datetime, timezone
import hashlib
import json
import math
from pathlib import Path
import re
import shutil
import subprocess
import sys

from sciquarry.ask import evidence_messages, inspect_citations
from sciquarry.evaluate import read_jsonl, sha256

VERSION = 'mlx-lm[train]==0.32.2'
SPLITS = ('train', 'valid', 'test')
HEX = re.compile(r'^[0-9a-f]{64}$')


def digest_record(record):
    """Bind a human review to all sample content except the review itself."""
    content = {k: v for k, v in record.items() if k != 'review'}
    encoded = json.dumps(content, ensure_ascii=False, sort_keys=True, separators=(',', ':')).encode()
    return hashlib.sha256(encoded).hexdigest()


def required_text(obj, key, where):
    value = obj.get(key)
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f'{where}: {key} must be a nonempty string')
    return value


def validate(records, kind, reserved=(), reserved_hashes=()):
    if kind not in ('synthetic', 'reviewed') or not records:
        raise ValueError('a nonempty synthetic or reviewed dataset is required')
    ids, questions, groups, sources, source_hashes, passages = set(), set(), {}, {}, {}, {}
    counts = dict.fromkeys(SPLITS, 0)
    for row in records:
        if not isinstance(row, dict):
            raise ValueError('each sample must be an object')
        rid = required_text(row, 'id', 'sample')
        split = row.get('split')
        if rid in ids or split not in SPLITS:
            raise ValueError(f'{rid}: duplicate ID or invalid split')
        ids.add(rid); counts[split] += 1
        if row.get('kind') != kind:
            raise ValueError(f'{rid}: dataset kind mismatch')
        q = required_text(row, 'question', rid)
        normalized = ' '.join(q.split()).casefold()
        if normalized in questions:
            raise ValueError(f'{rid}: duplicate question')
        questions.add(normalized)
        group = required_text(row, 'group_id', rid)
        if group in groups and groups[group] != split:
            raise ValueError(f'{rid}: group spans splits')
        groups[group] = split
        answer = required_text(row, 'answer', rid)
        answerability = row.get('answerability')
        if answerability not in ('answerable', 'insufficient_evidence'):
            raise ValueError(f'{rid}: invalid answerability')
        evidence = row.get('evidence')
        if not isinstance(evidence, list) or not evidence:
            raise ValueError(f'{rid}: at least one evidence passage is required')
        passage_ids = set()
        for passage in evidence:
            if not isinstance(passage, dict):
                raise ValueError(f'{rid}: evidence must be an object')
            sid = required_text(passage, 'source_id', rid)
            pid = required_text(passage, 'id', rid)
            passage_text = ' '.join(required_text(passage, 'text', rid).split()).casefold()
            if passage_text in passages and passages[passage_text] != split:
                raise ValueError(f'{rid}: identical evidence spans splits')
            passages[passage_text] = split
            if not re.fullmatch(r'[A-Za-z0-9_-]+:[0-9.]+:p[0-9]+', pid) or not pid.startswith(sid + ':') or pid in passage_ids:
                raise ValueError(f'{rid}: invalid or duplicate passage ID')
            passage_ids.add(pid)
            if sid in sources and sources[sid] != split:
                raise ValueError(f'{rid}: source spans splits')
            sources[sid] = split
            if kind == 'reviewed':
                if sid in reserved and split == 'train':
                    raise ValueError(f'{rid}: source {sid} is reserved for existing development evaluation')
                required_text(passage, 'source_url', rid)
                required_text(passage, 'locator', rid)
                required_text(passage, 'license', rid)
                source_hash = str(passage.get('source_sha256', ''))
                if passage.get('training_use_permitted') is not True or not HEX.fullmatch(source_hash):
                    raise ValueError(f'{rid}: source digest and explicit training permission required')
                if split == 'train' and source_hash in reserved_hashes:
                    raise ValueError(f'{rid}: source digest is reserved for existing development evaluation')
                if source_hash in source_hashes and source_hashes[source_hash] != split:
                    raise ValueError(f'{rid}: source digest spans splits')
                source_hashes[source_hash] = split
        citations = inspect_citations(answer, passage_ids)
        if citations['unknown_citations'] or citations['malformed_citations'] or (answerability == 'answerable' and not citations['valid_citations']):
            raise ValueError(f'{rid}: answer has missing, unknown or malformed citations')
        if kind == 'reviewed':
            review = row.get('review')
            if not isinstance(review, dict) or review.get('status') != 'approved' or review.get('reviewer_kind') != 'human_domain_expert':
                raise ValueError(f'{rid}: domain expert approval required')
            required_text(review, 'reviewer', rid)
            required_text(review, 'reviewed_at', rid)
            if review.get('content_sha256') != digest_record(row):
                raise ValueError(f'{rid}: review content digest mismatch')
    if any(not counts[s] for s in SPLITS):
        raise ValueError('train, valid and test must each contain samples from separate groups')
    return counts


def write_json(path, obj):
    with path.open('x', encoding='utf-8') as f:
        json.dump(obj, f, ensure_ascii=False, indent=2)
        f.write('\n')


def prepare(input_path, output, kind, reserved, reserved_hashes=()):
    records = read_jsonl(input_path)
    counts = validate(records, kind, reserved, reserved_hashes)
    output.mkdir(parents=True, exist_ok=False)
    files = {}
    for split in SPLITS:
        path = output / (split + '.jsonl')
        with path.open('x', encoding='utf-8') as f:
            for row in records:
                if row['split'] == split:
                    messages = evidence_messages(row['question'], row['evidence'])
                    messages.append({'role': 'assistant', 'content': row['answer']})
                    f.write(json.dumps({'messages': messages}, ensure_ascii=False) + '\n')
        files[path.name] = sha256(path)
    snapshot = output / 'samples.jsonl'
    with snapshot.open('x', encoding='utf-8') as f:
        for row in records:
            f.write(json.dumps(row, ensure_ascii=False) + '\n')
    files[snapshot.name] = sha256(snapshot)
    manifest = {'schema': 1, 'kind': kind, 'counts': counts, 'input_sha256': sha256(input_path),
                'reserved_source_ids': sorted(reserved), 'reserved_source_sha256': sorted(reserved_hashes), 'files': files,
                'system_prompt_sha256': hashlib.sha256(evidence_messages('x', [])[0]['content'].encode()).hexdigest()}
    write_json(output / 'manifest.json', manifest)
    return manifest


def verify_prepared(path):
    with (path / 'manifest.json').open(encoding='utf-8') as f:
        manifest = json.load(f)
    names = {'train.jsonl', 'valid.jsonl', 'test.jsonl', 'samples.jsonl'}
    if manifest.get('schema') != 1 or set(manifest.get('files', {})) != names:
        raise ValueError('invalid prepared manifest')
    for name in names:
        if sha256(path / name) != manifest['files'][name]:
            raise ValueError(f'prepared file changed: {name}')
    rows = read_jsonl(path / 'samples.jsonl')
    if validate(rows, manifest['kind'], manifest.get('reserved_source_ids', ()), manifest.get('reserved_source_sha256', ())) != manifest['counts']:
        raise ValueError('sample counts changed')
    # The JSONL is derived data; do not trust checksums alone to prove correspondence.
    for split in SPLITS:
        expected = [{'messages': evidence_messages(r['question'], r['evidence']) +
                    [{'role': 'assistant', 'content': r['answer']}]} for r in rows if r['split'] == split]
        if read_jsonl(path / (split + '.jsonl')) != expected:
            raise ValueError(f'{split}: prepared messages do not match samples')
    return manifest


def reserved_sources():
    root = Path(__file__).resolve().parent.parent / 'data' / 'biomedical_qa'
    result = set()
    for name in ('dev_examples.jsonl', 'review_candidates_p05.jsonl'):
        for row in read_jsonl(root / name):
            result.update(row.get('source_ids', []))
            result.update(x['source_id'] for x in row.get('evidence', []) if x.get('source_id'))
    return result




def reserved_source_hashes():
    root = Path(__file__).resolve().parent.parent / 'data' / 'biomedical_qa'
    result = set()
    for name in ('dev_examples.jsonl', 'review_candidates_p05.jsonl'):
        for row in read_jsonl(root / name):
            result.update(x['source_sha256'] for x in row.get('evidence', []) if x.get('source_sha256'))
    return result


def model_hashes(model):
    return {p.name: sha256(p) for p in sorted(model.iterdir()) if p.is_file()
            and p.suffix in ('.json', '.safetensors', '.txt', '.model', '.jinja')}

def run_training(data, model, output, args):
    manifest = verify_prepared(data)
    if manifest['kind'] == 'reviewed':
        validate(read_jsonl(data / 'samples.jsonl'), 'reviewed', reserved_sources(), reserved_source_hashes())
    if not model.is_dir() or not (model / 'config.json').is_file():
        raise ValueError('model must be an existing local model directory')
    if min(args.iters, args.batch_size, args.num_layers, args.max_seq_length, args.save_every) < 1 or not math.isfinite(args.learning_rate) or args.learning_rate <= 0:
        raise ValueError('training parameters must be positive')
    if args.batch_size > min(manifest['counts']['train'], manifest['counts']['valid']):
        raise ValueError('batch size must not exceed train or validation sample count')
    output.mkdir(parents=True, exist_ok=False)
    base_hashes = model_hashes(model)
    train_data = output / 'training_data'
    train_data.mkdir()
    for name in ('train.jsonl', 'valid.jsonl'):
        shutil.copyfile(data / name, train_data / name)
    uv = ['uvx', '--python', '3.11', '--from', VERSION]
    check = uv + ['python', '-m', 'sciquarry.sft_mlx', '--data', str(train_data.resolve()), '--model', str(model.resolve()), '--max-seq-length', str(args.max_seq_length)]
    command = uv + ['mlx_lm.lora', '--model', str(model.resolve()), '--data', str(train_data.resolve()), '--train', '--fine-tune-type', 'lora', '--mask-prompt', '--grad-checkpoint', '--adapter-path', str((output / 'adapter').resolve()), '--iters', str(args.iters), '--batch-size', str(args.batch_size), '--num-layers', str(args.num_layers), '--max-seq-length', str(args.max_seq_length), '--learning-rate', str(args.learning_rate), '--save-every', str(args.save_every), '--steps-per-report', '1', '--steps-per-eval', str(args.eval_every), '--val-batches', '-1', '--seed', str(args.seed)]
    record = {'schema': 1, 'status': 'started', 'started_at': datetime.now(timezone.utc).isoformat(),
              'dataset_kind': manifest['kind'], 'prepared_manifest_sha256': sha256(data / 'manifest.json'),
              'prepared_files': manifest['files'], 'model_path': str(model.resolve()), 'model_files': base_hashes,
              'dependency': VERSION, 'code_sha256': {p.name: sha256(p) for p in (Path(__file__), Path(__file__).with_name('sft_mlx.py'), Path(__file__).with_name('ask.py'))}, 'preflight_command': check, 'train_command': command}
    write_json(output / 'run.json', record)
    status = 'failed'
    try:
        with (output / 'training.log').open('x', encoding='utf-8') as log:
            for cmd in (check, command):
                print('Running:', ' '.join(cmd), flush=True)
                result = subprocess.run(cmd, stdout=log, stderr=subprocess.STDOUT)
                log.flush()
                if result.returncode:
                    raise ValueError(f'command failed ({result.returncode}); see {output / "training.log"}')
        adapter = output / 'adapter' / 'adapters.safetensors'
        if not adapter.is_file():
            raise ValueError('training completed without adapter weights')
        record['adapter_sha256'] = sha256(adapter)
        record['adapter_config_sha256'] = sha256(output / 'adapter' / 'adapter_config.json')
        status = 'completed'
    finally:
        record['status'] = status
        record['finished_at'] = datetime.now(timezone.utc).isoformat()
        (output / 'run.json').write_text(json.dumps(record, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
    return record


def main(argv=None):
    p = argparse.ArgumentParser(description=__doc__)
    sub = p.add_subparsers(dest='cmd', required=True)
    h = sub.add_parser('review-hash'); h.add_argument('--samples', type=Path, required=True)
    d = sub.add_parser('prepare'); d.add_argument('--samples', type=Path, required=True); d.add_argument('--output', type=Path, required=True); d.add_argument('--kind', choices=('synthetic', 'reviewed'), required=True)
    t = sub.add_parser('train'); t.add_argument('--data', type=Path, required=True); t.add_argument('--model', type=Path, required=True); t.add_argument('--output', type=Path, required=True)
    t.add_argument('--iters', type=int, default=100); t.add_argument('--batch-size', type=int, default=1); t.add_argument('--num-layers', type=int, default=8); t.add_argument('--max-seq-length', type=int, default=2048); t.add_argument('--learning-rate', type=float, default=1e-5); t.add_argument('--save-every', type=int, default=25); t.add_argument('--eval-every', type=int, default=25); t.add_argument('--seed', type=int, default=0)
    args = p.parse_args(argv)
    try:
        if args.cmd == 'review-hash':
            result = {r['id']: digest_record(r) for r in read_jsonl(args.samples)}
        elif args.cmd == 'prepare':
            result = prepare(args.samples, args.output, args.kind, reserved_sources() if args.kind == 'reviewed' else (), reserved_source_hashes() if args.kind == 'reviewed' else ())
        else:
            if args.eval_every < 1: raise ValueError('eval-every must be positive')
            result = run_training(args.data, args.model, args.output, args)
        print(json.dumps(result, ensure_ascii=False, indent=2))
    except (OSError, ValueError, KeyError, TypeError, json.JSONDecodeError) as exc:
        print(f'Error: {exc}', file=sys.stderr); return 1
    return 0


if __name__ == '__main__':
    sys.exit(main())
