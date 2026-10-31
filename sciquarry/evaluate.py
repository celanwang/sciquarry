"""Run a traceable development evaluation of retrieval or evidence-bound answers."""

import argparse
from collections import Counter
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import sys
import time

from sciquarry.ask import answer_with_evidence, local_chat_url
from sciquarry.retrieval import search


def sha256(path):
    digest = hashlib.sha256()
    with path.open("rb") as f:
        for block in iter(lambda: f.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def read_jsonl(path):
    with path.open(encoding="utf-8") as f:
        return [json.loads(line) for line in f if line.strip()]


def prepare(samples, records):
    """Fail closed when a sample's annotated evidence or provenance is missing."""
    ids = [r["id"] for r in records]
    if len(ids) != len(set(ids)):
        raise ValueError("index contains duplicate passage IDs")
    by_id = {r["id"]: r for r in records}
    sample_ids = [s["id"] for s in samples]
    if not sample_ids or len(sample_ids) != len(set(sample_ids)):
        raise ValueError("samples are empty or contain duplicate IDs")
    for sample in samples:
        annotations = sample["evidence"]
        if not annotations:
            raise ValueError(f"{sample['id']}: no annotated evidence")
        seen = set()
        for annotation in annotations:
            pid = annotation["passage_id"]
            if pid in seen or pid not in by_id:
                raise ValueError(f"{sample['id']}: duplicate or missing passage {pid}")
            seen.add(pid)
            record = by_id[pid]
            if (annotation["source_id"] != record["source_id"] or
                    annotation["source_sha256"] != record["source_sha256"]):
                raise ValueError(f"{sample['id']}: source provenance mismatch for {pid}")
    return by_id


def retrieval_result(sample, records, top_k):
    expected = {e["passage_id"] for e in sample["evidence"]}
    found = search(records, sample["question"], top_k)
    returned = [x["id"] for x in found]
    matches = sorted(expected.intersection(returned))
    return {"sample_id": sample["id"], "answerability": sample["answerability"],
            "question": sample["question"], "expected_passage_ids": sorted(expected),
            "retrieved": [{"id": x["id"], "score": x["score"]} for x in found],
            "matched_passage_ids": matches, "any_hit": bool(matches),
            "all_hit": len(matches) == len(expected)}


def answer_result(sample, by_id, model, base_url, no_thinking):
    evidence = [by_id[e["passage_id"]] for e in sample["evidence"]]
    start = time.monotonic()
    result = answer_with_evidence(evidence, sample["question"], model, base_url,
                                  no_thinking=no_thinking)
    return {"sample_id": sample["id"], "question": sample["question"],
            "answerability": sample["answerability"],
            "provided_passage_ids": [r["id"] for r in evidence],
            "answer": result["answer"], "citation_status": result["citation_status"],
            "unknown_citations": result["unknown_citations"],
            "finish_reason": result.get("finish_reason"),
            "system_fingerprint": result.get("system_fingerprint"),
            "usage": result.get("usage"), "elapsed_seconds": round(time.monotonic() - start, 3),
            "review": {"status": "pending_human_review"}}


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("mode", choices=("retrieval", "answer"))
    parser.add_argument("--samples", type=Path, required=True)
    parser.add_argument("--index", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--top-k", type=int, default=3)
    parser.add_argument("--model")
    parser.add_argument("--base-url", default="http://127.0.0.1:8001/v1")
    parser.add_argument("--no-thinking", action="store_true")
    args = parser.parse_args(argv)
    try:
        if args.top_k < 1:
            raise ValueError("top-k must be at least 1")
        if args.mode == "answer":
            if not args.model:
                raise ValueError("--model is required for answer evaluation")
            local_chat_url(args.base_url)
        samples, records = read_jsonl(args.samples), read_jsonl(args.index)
        by_id = prepare(samples, records)
        meta = {"type": "metadata", "mode": args.mode, "created_at": datetime.now(timezone.utc).isoformat(),
                "sample_file": str(args.samples), "sample_sha256": sha256(args.samples),
                "index_file": str(args.index), "index_sha256": sha256(args.index),
                "code_sha256": {p: sha256(Path(p)) for p in ("sciquarry/ask.py", "sciquarry/retrieval.py", "sciquarry/evaluate.py")},
                "sample_count": len(samples), "top_k": args.top_k if args.mode == "retrieval" else None,
                "model": args.model if args.mode == "answer" else None,
                "base_url": args.base_url if args.mode == "answer" else None,
                "no_thinking": args.no_thinking if args.mode == "answer" else None,
                "temperature": 0 if args.mode == "answer" else None,
                "max_tokens": 1024 if args.mode == "answer" else None,
                "notice": "Development examples; source annotations are not expert reviewed."}
        args.output.parent.mkdir(parents=True, exist_ok=True)
        with args.output.open("x", encoding="utf-8") as out:
            def write(value):
                out.write(json.dumps(value, ensure_ascii=False) + "\n")
                out.flush()
            write(meta)
            successes, failures, any_hits, all_hits = 0, 0, 0, 0
            finish_reasons = Counter()
            for sample in samples:
                try:
                    if args.mode == "retrieval":
                        item = retrieval_result(sample, records, args.top_k)
                        any_hits += item["any_hit"]
                        all_hits += item["all_hit"]
                    else:
                        item = answer_result(sample, by_id, args.model, args.base_url, args.no_thinking)
                        finish_reasons[str(item["finish_reason"])] += 1
                    successes += 1
                    write({"type": "result", **item})
                except (OSError, ValueError, KeyError, TypeError) as exc:
                    failures += 1
                    write({"type": "error", "sample_id": sample["id"], "error": str(exc)})
                print(f"{successes + failures}/{len(samples)} {sample['id']}", file=sys.stderr, flush=True)
            summary = {"type": "summary", "successes": successes, "failures": failures}
            if args.mode == "retrieval":
                summary.update(any_hit_count=any_hits, all_hit_count=all_hits, denominator=successes)
            else:
                summary.update(finish_reasons=dict(finish_reasons), answers_automatically_scored=False)
            write(summary)
        print(json.dumps(summary, ensure_ascii=False))
        return 1 if failures else 0
    except (OSError, ValueError, KeyError, TypeError, json.JSONDecodeError) as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
