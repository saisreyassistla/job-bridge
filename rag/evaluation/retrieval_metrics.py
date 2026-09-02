"""
Retrieval metrics evaluator — measures Recall@K, Precision@K, MRR,
NDCG@K, and Hit Rate across BM25, dense, RRF, and reranked results.

Usage:
  python evaluation/retrieval_metrics.py
  python evaluation/retrieval_metrics.py --k 5
  python evaluation/retrieval_metrics.py --output evaluation/results/retrieval_report.json
"""

from __future__ import annotations
import os
import sys
import json
import math
import argparse
from pathlib import Path
from datetime import datetime

sys.path.insert(0, str(Path(__file__).parent.parent))
try:
    from dotenv import load_dotenv
except ImportError:
    def load_dotenv():
        return False
load_dotenv(Path(__file__).resolve().parents[2] / ".env", override=True)
SERVICE_API_KEY = os.getenv("SERVICE_API_KEY", "")

# ── Default labeled retrieval dataset ────────────────────────────────────────
# relevant_sources = source filenames that SHOULD appear in top-K results.
# Update these to match your actual ingested document filenames.

DEFAULT_RETRIEVAL_DATASET = [
    {
        "question": "What are Amazon's leadership principles?",
        "relevant_sources": ["Interview_Questions_Bank_amz.pdf", "./data/raw/Interview_Questions_Bank_amz.pdf", "data/raw/Interview_Questions_Bank_amz.pdf"],
    },
    {
        "question": "How should I prepare for a behavioral interview at Amazon?",
        "relevant_sources": ["Interview_Questions_Bank_amz.pdf", "./data/raw/Interview_Questions_Bank_amz.pdf", "data/raw/Interview_Questions_Bank_amz.pdf"],
    },
    {
        "question": "What is the STAR method for interviews?",
        "relevant_sources": ["Interview_Questions_Bank_amz.pdf", "./data/raw/Interview_Questions_Bank_amz.pdf", "data/raw/Interview_Questions_Bank_amz.pdf"],
    },
    {
        "question": "What is customer obsession at Amazon?",
        "relevant_sources": ["Interview_Questions_Bank_amz.pdf", "./data/raw/Interview_Questions_Bank_amz.pdf", "data/raw/Interview_Questions_Bank_amz.pdf"],
    },
    {
        "question": "How does Amazon use leadership principles in hiring?",
        "relevant_sources": ["Interview_Questions_Bank_amz.pdf", "./data/raw/Interview_Questions_Bank_amz.pdf", "data/raw/Interview_Questions_Bank_amz.pdf"],
    },
]


# ── Metric computations ───────────────────────────────────────────────────────

def is_relevant(chunk: dict, relevant_sources: list[str]) -> bool:
    source = Path(chunk.get("source") or "").name.lower()
    return any(Path(rs).name.lower() == source for rs in relevant_sources)


def relevant_source_keys(relevant_sources: list[str]) -> set[str]:
    return {Path(source).name.lower() for source in relevant_sources}


def precision_at_k(chunks: list[dict], relevant_sources: list[str], k: int) -> float:
    hits = sum(1 for c in chunks[:k] if is_relevant(c, relevant_sources))
    return hits / k if k > 0 else 0.0


def recall_at_k(chunks: list[dict], relevant_sources: list[str], k: int) -> float:
    expected = relevant_source_keys(relevant_sources)
    found = {
        Path(c.get("source") or "").name.lower()
        for c in chunks[:k]
        if is_relevant(c, relevant_sources)
    }
    return len(found & expected) / len(expected) if expected else 0.0


def hit_rate_at_k(chunks: list[dict], relevant_sources: list[str], k: int) -> float:
    return 1.0 if any(is_relevant(c, relevant_sources) for c in chunks[:k]) else 0.0


def mrr(chunks: list[dict], relevant_sources: list[str]) -> float:
    for rank, chunk in enumerate(chunks, start=1):
        if is_relevant(chunk, relevant_sources):
            return 1.0 / rank
    return 0.0


def ndcg_at_k(chunks: list[dict], relevant_sources: list[str], k: int) -> float:
    def dcg(rels):
        return sum(r / math.log2(i + 2) for i, r in enumerate(rels))
    rels  = [1 if is_relevant(c, relevant_sources) else 0 for c in chunks[:k]]
    ideal = sorted(rels, reverse=True)
    d, id_ = dcg(rels), dcg(ideal)
    return d / id_ if id_ > 0 else 0.0


# ── Pipeline retrieval via /report endpoint ───────────────────────────────────

def retrieve_all_stages(question: str, k: int) -> dict:
    """Call /report endpoint and extract per-stage chunk lists."""
    import requests
    RAG_URL = os.getenv("RAG_SERVER_URL", "http://localhost:8000")

    r = requests.post(
        f"{RAG_URL}/report",
        headers={"x-service-key": SERVICE_API_KEY},
        json={"question": question},
        timeout=90,
    )
    r.raise_for_status()
    data   = r.json()
    stages = data.get("stages", {})

    return {
        "bm25":     stages.get("bm25",     [])[:k],
        "dense":    stages.get("dense",    [])[:k],
        "rrf":      stages.get("rrf",      [])[:k],
        "reranked": stages.get("reranked", [])[:k],
    }


# ── Evaluation loop ───────────────────────────────────────────────────────────

def evaluate_retrieval(dataset: list[dict], k: int) -> dict:
    stage_names  = ["bm25", "dense", "rrf", "reranked"]
    metric_names = ["precision", "recall", "hit_rate", "mrr", "ndcg"]
    scores = {s: {m: [] for m in metric_names} for s in stage_names}

    print(f"\nEvaluating retrieval on {len(dataset)} questions (k={k})...")
    for i, item in enumerate(dataset, 1):
        question = item["question"]
        relevant = item["relevant_sources"]
        print(f"  [{i}/{len(dataset)}] {question[:65]}...")

        try:
            stage_chunks = retrieve_all_stages(question, k)
        except Exception as e:
            print(f"    ⚠️  Failed: {e}")
            continue

        for stage, chunks in stage_chunks.items():
            scores[stage]["precision"].append(precision_at_k(chunks, relevant, k))
            scores[stage]["recall"].append(recall_at_k(chunks, relevant, k))
            scores[stage]["hit_rate"].append(hit_rate_at_k(chunks, relevant, k))
            scores[stage]["mrr"].append(mrr(chunks, relevant))
            scores[stage]["ndcg"].append(ndcg_at_k(chunks, relevant, k))

    return {
        stage: {
            metric: round(sum(vals) / len(vals), 4) if vals else 0.0
            for metric, vals in metrics.items()
        }
        for stage, metrics in scores.items()
    }


# ── Report ────────────────────────────────────────────────────────────────────

def print_retrieval_report(results: dict, k: int):
    print("\n" + "═" * 72)
    print(f"  RETRIEVAL METRICS REPORT — JobBridge RAG Pipeline  (k={k})")
    print("═" * 72)
    print(f"  {'Stage':<12} {'Precision':>10} {'Recall':>10} "
          f"{'Hit Rate':>10} {'MRR':>10} {'NDCG':>10}")
    print(f"  {'─'*12} {'─'*10} {'─'*10} {'─'*10} {'─'*10} {'─'*10}")

    for stage in ["bm25", "dense", "rrf", "reranked"]:
        m = results[stage]
        print(f"  {stage:<12} {m['precision']:>10.4f} {m['recall']:>10.4f} "
              f"{m['hit_rate']:>10.4f} {m['mrr']:>10.4f} {m['ndcg']:>10.4f}")

    print("═" * 72)
    rrf_ndcg    = results["rrf"]["ndcg"]
    bm25_ndcg   = results["bm25"]["ndcg"]
    dense_ndcg  = results["dense"]["ndcg"]
    rerank_ndcg = results["reranked"]["ndcg"]
    print(f"\n  RRF lift over BM25 alone:     {rrf_ndcg - bm25_ndcg:+.4f}")
    print(f"  RRF lift over Dense alone:    {rrf_ndcg - dense_ndcg:+.4f}")
    print(f"  Reranker lift over RRF:       {rerank_ndcg - rrf_ndcg:+.4f}")


def save_retrieval_report(results: dict, k: int, output_path: str):
    Path(output_path).parent.mkdir(parents=True, exist_ok=True)
    with open(output_path, "w") as f:
        json.dump({"timestamp": datetime.now().isoformat(),
                   "k": k, "results": results}, f, indent=2)
    print(f"\n  Report saved to {output_path}")


# ── Main ──────────────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--k",       type=int, default=5)
    parser.add_argument("--dataset", type=str)
    parser.add_argument("--output",  type=str,
                        default="evaluation/results/retrieval_report.json")
    args = parser.parse_args()

    dataset = json.load(open(args.dataset)) if args.dataset \
              else DEFAULT_RETRIEVAL_DATASET

    results = evaluate_retrieval(dataset, args.k)
    print_retrieval_report(results, args.k)
    save_retrieval_report(results, args.k, args.output)


if __name__ == "__main__":
    main()
