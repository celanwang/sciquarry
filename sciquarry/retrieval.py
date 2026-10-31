"""Build a traceable paragraph index and search it with a lexical baseline."""

import argparse
from collections import Counter
import hashlib
import json
import math
from pathlib import Path
import re
import sys
import xml.etree.ElementTree as ET


def _text(element):
    # JATS may embed full figures or tables inside a paragraph. They have their
    # own evidence context and must not be silently flattened into body text.
    excluded = {"fig", "fig-group", "table-wrap", "table-wrap-group", "supplementary-material"}

    def parts(node):
        if node.text:
            yield node.text
        for child in node:
            if child.tag.rsplit("}", 1)[-1] not in excluded:
                yield from parts(child)
            if child.tail:
                yield child.tail

    return " ".join("".join(parts(element)).split())


def index_article(path, source_id, expected_pmcid, source_url):
    """Extract body paragraphs from one JATS article, preserving source locations."""
    raw = path.read_bytes()
    root = ET.fromstring(raw)
    pmcids = {"PMC" + (e.text or "").strip().replace("PMC", "", 1)
              for e in root.findall("./front/article-meta/article-id")
              if e.get("pub-id-type") in {"pmc", "pmcid"}}
    if expected_pmcid not in pmcids:
        raise ValueError("XML PMCID does not match expected source: " + expected_pmcid)
    body = root.find("./body")
    if body is None:
        raise ValueError("XML has no article body")
    digest = hashlib.sha256(raw).hexdigest()
    records = []

    def visit(section, titles, position):
        title = section.find("./title")
        title_text = _text(title) if title is not None else ""
        section_titles = titles + ([title_text] if title_text else [])
        # The position path also works for articles with missing or duplicate section IDs.
        section_id = section.get("id")
        for number, paragraph in enumerate(section.findall("./p"), 1):
            content = _text(paragraph)
            if not content:
                continue
            records.append({
                "id": f"{source_id}:{position}:p{number}",
                "source_id": source_id,
                "pmcid": expected_pmcid,
                "source_url": source_url,
                "source_sha256": digest,
                "section_path": section_titles,
                "section_id": section_id,
                "section_position": position,
                "paragraph": number,
                "text": content,
            })
        for number, child in enumerate(section.findall("./sec"), 1):
            visit(child, section_titles, f"{position}.{number}")

    for number, section in enumerate(body.findall("./sec"), 1):
        visit(section, [], str(number))
    if not records:
        raise ValueError("No section paragraphs found in XML body")
    return records


def tokenize(text):
    # English lexical search and CJK character bigrams.
    pieces = re.findall(r"[a-z0-9]+|[\u3400-\u9fff]+", text.lower())
    tokens = []
    for piece in pieces:
        if "\u3400" <= piece[0] <= "\u9fff" and len(piece) > 1:
            tokens.extend(piece[i:i + 2] for i in range(len(piece) - 1))
        else:
            tokens.append(piece)
    return tokens


# Deliberately narrow vocabulary for the initial CML/imatinib pilot.
ZH_ALIASES = {
    "伊马替尼": "imatinib STI571",
    "慢性髓性白血病": "chronic myeloid leukemia CML",
    "细胞": "cell cells",
    "竞争": "competition competitive",
    "野生型": "wild type WT",
    "混合": "mixed mixture",
    "流式": "flow cytometry",
    "处理": "treated treatment",
    "多久": "duration time hours",
    "小时": "hours h",
    "增殖": "proliferation growth",
    "凋亡": "apoptosis",
    "耐药": "resistant resistance",
    "对照": "control comparison",
    "阳性": "positive",
    "患者": "patient patients",
    "剂量": "dose dosage",
    "实验": "experiment experimental",
    "筛选": "screen screening screened",
    "初筛": "screen screened",
    "候选": "candidate candidates selected",
    "复测": "retest retested",
    "重复": "repeat repeated retest retested replicate replicates",
    "分化": "differentiation",
    "分析": "analysis assay",
    "浓度": "concentration concentrations",
    "药物": "drug drugs compound compounds",
    "体外": "vitro",
    "初始": "initial initially mixed",
    "比例": "ratio",
    "显著": "significant significantly",
    "比较": "compare compared comparison",
}


def expand_query(query):
    """Add matching English keywords; not a general Chinese translator."""
    additions = [translation for phrase, translation in ZH_ALIASES.items() if phrase in query]
    return " ".join([query] + additions)


def search(records, query, top_k=5):
    """BM25 over paragraph text and headings; zero-overlap queries return no results."""
    if top_k < 1:
        raise ValueError("top_k must be at least 1")
    terms = set(tokenize(expand_query(query)))
    if not terms or not records:
        return []
    documents = [tokenize(" ".join(record["section_path"]) + " " + record["text"])
                 for record in records]
    avg_length = sum(map(len, documents)) / len(documents)
    if not avg_length:
        return []
    frequencies = [Counter(doc) for doc in documents]
    doc_freq = {term: sum(term in doc for doc in frequencies) for term in terms}
    results = []
    for record, doc, counts in zip(records, documents, frequencies):
        score = 0.0
        for term in terms:
            freq = counts[term]
            if freq:
                idf = math.log(1 + (len(documents) - doc_freq[term] + 0.5) / (doc_freq[term] + 0.5))
                score += idf * (freq * 2.2) / (freq + 1.2 * (0.25 + 0.75 * len(doc) / avg_length))
        if score > 0:
            results.append({**record, "score": round(score, 6)})
    return sorted(results, key=lambda item: (-item["score"], item["id"]))[:top_k]


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)
    ingest = commands.add_parser("ingest", help="Index one local JATS XML article")
    ingest.add_argument("xml", type=Path)
    ingest.add_argument("--source-id", required=True)
    ingest.add_argument("--pmcid", required=True)
    ingest.add_argument("--source-url", required=True)
    ingest.add_argument("--output", type=Path, required=True)
    query = commands.add_parser("search", help="Search an indexed article")
    query.add_argument("index", type=Path)
    query.add_argument("query")
    query.add_argument("--top-k", type=int, default=5)
    args = parser.parse_args(argv)
    try:
        if args.command == "ingest":
            if args.xml.resolve() == args.output.resolve():
                raise ValueError("Input and output must be different files")
            records = index_article(args.xml, args.source_id, args.pmcid, args.source_url)
            args.output.parent.mkdir(parents=True, exist_ok=True)
            with args.output.open("w", encoding="utf-8") as output:
                for record in records:
                    output.write(json.dumps(record, ensure_ascii=False) + "\n")
            print(f"Indexed {len(records)} paragraphs to {args.output}")
        else:
            with args.index.open(encoding="utf-8") as source:
                records = [json.loads(line) for line in source if line.strip()]
            print(json.dumps(search(records, args.query, args.top_k), ensure_ascii=False, indent=2))
    except (OSError, ValueError, KeyError, ET.ParseError, json.JSONDecodeError) as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
