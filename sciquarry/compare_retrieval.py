"""Compare the current retriever with a historical committed version on one corpus."""

import argparse
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import re
import subprocess
import sys
import types

from sciquarry.evaluate import prepare, read_jsonl, sha256
from sciquarry.retrieval import search


def historical_search(revision):
    # Accept only an explicit commit ID, so arbitrary options or git expressions
    # cannot be passed to git show. The repository code at that commit is run.
    if not re.fullmatch(r"[0-9a-fA-F]{7,40}", revision):
        raise ValueError("baseline revision must be a 7–40 character hexadecimal commit ID")
    result = subprocess.run(["git", "show", revision + ":sciquarry/retrieval.py"],
                            check=True, capture_output=True)
    module = types.ModuleType("historical_retrieval")
    exec(compile(result.stdout, revision + ":sciquarry/retrieval.py", "exec"), module.__dict__)
    return module.search, hashlib.sha256(result.stdout).hexdigest()


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--samples", type=Path, required=True)
    parser.add_argument("--index", type=Path, required=True)
    parser.add_argument("--baseline-revision", required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--top-k", type=int, default=3)
    args = parser.parse_args(argv)
    try:
        if args.top_k < 1:
            raise ValueError("top-k must be at least 1")
        samples, records = read_jsonl(args.samples), read_jsonl(args.index)
        prepare(samples, records)
        baseline_search, baseline_hash = historical_search(args.baseline_revision)
        args.output.parent.mkdir(parents=True, exist_ok=True)
        with args.output.open("x", encoding="utf-8") as out:
            def write(value):
                out.write(json.dumps(value, ensure_ascii=False) + "\n")
            write({"type":"metadata", "created_at":datetime.now(timezone.utc).isoformat(),
                   "samples":str(args.samples), "samples_sha256":sha256(args.samples),
                   "index":str(args.index), "index_sha256":sha256(args.index), "top_k":args.top_k,
                   "baseline_revision":args.baseline_revision, "baseline_retriever_sha256":baseline_hash,
                   "current_retriever_sha256":sha256(Path('sciquarry/retrieval.py')),
                   "comparison_code_sha256":sha256(Path('sciquarry/compare_retrieval.py')),
                   "notice":"Exploratory article-level candidates; no expert review or verified data independence."})
            before_any=before_all=after_any=after_all=0
            for sample in samples:
                expected={e['passage_id'] for e in sample['evidence']}
                before=baseline_search(records,sample['question'],args.top_k)
                after=search(records,sample['question'],args.top_k)
                a={r['id'] for r in before}; b={r['id'] for r in after}
                before_any += bool(expected & a); before_all += expected <= a
                after_any += bool(expected & b); after_all += expected <= b
                write({'type':'result','sample_id':sample['id'],'question':sample['question'],
                       'expected':sorted(expected),
                       'before':[{'id':x['id'],'score':x['score']} for x in before],
                       'after':[{'id':x['id'],'score':x['score']} for x in after],
                       'before_any':bool(expected & a),'before_all':expected <= a,
                       'after_any':bool(expected & b),'after_all':expected <= b})
            summary={'type':'summary','count':len(samples),'before_any':before_any,'before_all':before_all,
                     'after_any':after_any,'after_all':after_all}
            write(summary)
        print(json.dumps(summary,ensure_ascii=False))
        return 0
    except (OSError, ValueError, KeyError, TypeError, subprocess.CalledProcessError) as exc:
        print(f'Error: {exc}',file=sys.stderr)
        return 1


if __name__ == '__main__':
    sys.exit(main())
