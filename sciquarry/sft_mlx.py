"""Preflight actual MLX-LM chat masks and reject truncation before training."""
import argparse
import json
import importlib.metadata
import platform
from pathlib import Path
import sys


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--data', type=Path, required=True)
    p.add_argument('--model', type=Path, required=True)
    p.add_argument('--max-seq-length', type=int, required=True)
    a = p.parse_args()
    print('Python:', platform.python_version(), 'macOS:', platform.mac_ver()[0], 'architecture:', platform.machine())
    for name in ('mlx-lm', 'mlx', 'transformers', 'numpy', 'safetensors'):
        print(name + ':', importlib.metadata.version(name))
    from mlx_lm.tuner.datasets import ChatDataset
    from mlx_lm.utils import load_tokenizer
    tokenizer = load_tokenizer(a.model)
    for split in ('train', 'valid'):
        records = [json.loads(line) for line in (a.data / (split + '.jsonl')).read_text().splitlines() if line.strip()]
        dataset = ChatDataset(records, tokenizer, mask_prompt=True)
        sizes = []
        for i, row in enumerate(records):
            tokens, offset = dataset.process(row)
            prefix = tokenizer.apply_chat_template(row['messages'][:-1], add_generation_prompt=True, return_dict=False)
            if tokens[:offset] != prefix or offset <= 0 or offset >= len(tokens) - 1:
                raise ValueError(f'{split} row {i + 1}: invalid prompt mask or template prefix')
            if len(tokens) > a.max_seq_length:
                raise ValueError(f'{split} row {i + 1}: {len(tokens)} tokens exceeds max sequence length {a.max_seq_length}')
            sizes.append(len(tokens))
        print(f'{split}: {len(sizes)} examples, max {max(sizes)} tokens; prompt mask checked', flush=True)
    return 0


if __name__ == '__main__':
    sys.exit(main())
