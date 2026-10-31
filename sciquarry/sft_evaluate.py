"""Evaluate a base model or a recorded LoRA adapter on the held-out SFT split."""
import argparse
from datetime import datetime, timezone
import importlib.metadata
import json
from pathlib import Path
import subprocess
import sys

from sciquarry.ask import evidence_messages, inspect_citations, review_flags
from sciquarry.evaluate import read_jsonl, sha256
from sciquarry.sft import VERSION, model_hashes, verify_prepared, write_json


def compare(before, after):
    a, b = read_jsonl(before), read_jsonl(after)
    for rows in (a, b):
        if len(rows) < 3 or rows[0].get('type') != 'metadata' or rows[-1].get('type') != 'summary' or rows[-1].get('count') != len(rows)-2:
            raise ValueError('evaluation is incomplete')
    for key in ('data_manifest_sha256', 'model_files', 'max_tokens', 'temperature', 'no_thinking', 'packages'):
        if a[0].get(key) != b[0].get(key):
            raise ValueError(f'evaluation configuration differs: {key}')
    if a[0].get('adapter_sha256') is not None or not b[0].get('adapter_sha256'):
        raise ValueError('before must be base and after must use an adapter')
    if len(a) != len(b): raise ValueError('evaluation sample counts differ')
    rows = []
    seen = set()
    for x, y in zip(a[1:-1], b[1:-1]):
        if x.get('type') != 'result' or y.get('type') != 'result' or x.get('sample_id') != y.get('sample_id') or x.get('question') != y.get('question') or x.get('evidence_ids') != y.get('evidence_ids'):
            raise ValueError('evaluation sample or evidence differs')
        if x['sample_id'] in seen: raise ValueError('duplicate sample ID')
        seen.add(x['sample_id'])
        rows.append({'sample_id': x['sample_id'], 'question': x['question'], 'evidence_ids': x['evidence_ids'],
                     'before': x, 'after': y, 'review_status': 'pending_human_review',
                     'checks': ['事实是否由证据支持', '实验条件与数字是否正确', '引用是否支持对应事实', '证据不足时是否拒答', '是否超出证据范围或包含风险结论'],
                     'reviewer': None, 'verdict': None})
    return {'type': 'comparison', 'before_sha256': sha256(before), 'after_sha256': sha256(after),
            'data_kind': a[0]['data_kind'], 'limitations': 'Citation format and text differences do not establish factual correctness.', 'cases': rows}


def worker(args):
    from mlx_lm import load, stream_generate
    from mlx_lm.sample_utils import make_sampler
    manifest = verify_prepared(args.data)
    if args.max_tokens < 1: raise ValueError('max-tokens must be positive')
    if not args.model.is_dir() or not (args.model / 'config.json').is_file(): raise ValueError('local model required')
    hashes = model_hashes(args.model)
    adapter = None; adapter_sha = None
    if args.adapter_run:
        run = json.loads((args.adapter_run / 'run.json').read_text())
        adapter = args.adapter_run / 'adapter'
        weights = adapter / 'adapters.safetensors'
        adapter_sha = sha256(weights)
        if run.get('status') != 'completed' or run.get('adapter_sha256') != adapter_sha or run.get('adapter_config_sha256') != sha256(adapter / 'adapter_config.json') or run.get('model_files') != hashes or run.get('prepared_manifest_sha256') != sha256(args.data / 'manifest.json'):
            raise ValueError('adapter run, base model or prepared data does not match')
    rows = [r for r in read_jsonl(args.data / 'samples.jsonl') if r['split'] == 'test']
    packages = {name: importlib.metadata.version(name) for name in ('mlx-lm', 'mlx', 'transformers', 'numpy', 'safetensors')}
    metadata = {'type': 'metadata', 'data_kind': manifest['kind'], 'data_manifest_sha256': sha256(args.data / 'manifest.json'),
                'model_files': hashes, 'adapter_sha256': adapter_sha, 'max_tokens': args.max_tokens, 'temperature': 0,
                'no_thinking': True, 'packages': packages, 'count': len(rows), 'created_at': datetime.now(timezone.utc).isoformat()}
    with args.output.open('x', encoding='utf-8') as f:
        def emit(row):
            f.write(json.dumps(row, ensure_ascii=False) + '\n'); f.flush()
        emit(metadata)
        model, tokenizer = load(str(args.model.resolve()), adapter_path=str(adapter.resolve()) if adapter else None)
        for row in rows:
            prompt = tokenizer.apply_chat_template(evidence_messages(row['question'], row['evidence']), tokenize=True,
                                                   add_generation_prompt=True, enable_thinking=False)
            parts = list(stream_generate(model, tokenizer, prompt, max_tokens=args.max_tokens, sampler=make_sampler(temp=0)))
            answer = ''.join(p.text for p in parts)
            if not answer.strip(): raise ValueError(f"{row['id']}: empty model answer")
            emit({'type': 'result', 'sample_id': row['id'], 'question': row['question'],
                  'evidence_ids': [x['id'] for x in row['evidence']], 'answer': answer,
                  **inspect_citations(answer, {x['id'] for x in row['evidence']}), 'review_flags': review_flags(answer),
                  'finish_reason': parts[-1].finish_reason if parts else None, 'review_status': 'pending_human_review'})
        emit({'type': 'summary', 'count': len(rows)})


def main(argv=None):
    p = argparse.ArgumentParser(description=__doc__); sub = p.add_subparsers(dest='cmd', required=True)
    for name in ('run', 'worker'):
        a = sub.add_parser(name)
        for opt in ('data', 'model', 'output'): a.add_argument('--' + opt, type=Path, required=True)
        a.add_argument('--adapter-run', type=Path); a.add_argument('--max-tokens', type=int, default=512)
    c = sub.add_parser('compare'); c.add_argument('--before', type=Path, required=True); c.add_argument('--after', type=Path, required=True); c.add_argument('--output', type=Path, required=True)
    args = p.parse_args(argv)
    try:
        if args.cmd == 'compare': write_json(args.output, compare(args.before, args.after))
        elif args.cmd == 'worker': worker(args)
        else:
            verify_prepared(args.data)
            if args.output.exists(): raise ValueError('output already exists')
            cmd = ['uvx', '--python', '3.11', '--from', VERSION, 'python', '-m', 'sciquarry.sft_evaluate', 'worker', '--data', str(args.data.resolve()), '--model', str(args.model.resolve()), '--output', str(args.output.resolve()), '--max-tokens', str(args.max_tokens)]
            if args.adapter_run: cmd += ['--adapter-run', str(args.adapter_run.resolve())]
            result = subprocess.run(cmd)
            if result.returncode: raise ValueError('evaluation worker failed; incomplete output may be retained')
            print('Evaluation saved:', args.output)
    except (OSError, ValueError, KeyError, TypeError, json.JSONDecodeError) as exc:
        print(f'Error: {exc}', file=sys.stderr); return 1
    return 0


if __name__ == '__main__': sys.exit(main())
