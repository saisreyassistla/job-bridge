"""
run_all.py — Run all four evaluation scripts in sequence and produce
a combined summary report.

Usage:
  python evaluation/run_all.py
  python evaluation/run_all.py --skip-retrieval --queries 3
  python evaluation/run_all.py --data-dir ./data/raw
"""

from __future__ import annotations
import os
import sys
import json
import argparse
import subprocess
from pathlib import Path
from datetime import datetime

sys.path.insert(0, str(Path(__file__).parent.parent))
from dotenv import load_dotenv
load_dotenv()

RESULTS_DIR = Path("evaluation/results")


def run(script: str, extra_args: list[str] = []) -> bool:
    cmd = [sys.executable, f"evaluation/{script}"] + extra_args
    print(f"\n{'─'*60}")
    print(f"  Running: {' '.join(cmd)}")
    print(f"{'─'*60}")
    result = subprocess.run(cmd)
    return result.returncode == 0


def summarize():
    RESULTS_DIR.mkdir(parents=True, exist_ok=True)
    summary = {"timestamp": datetime.now().isoformat(), "reports": {}}

    for report_file in RESULTS_DIR.glob("*.json"):
        if report_file.stem == "summary":
            continue
        try:
            with open(report_file) as f:
                summary["reports"][report_file.stem] = json.load(f)
        except Exception:
            pass

    summary_path = RESULTS_DIR / "summary.json"
    with open(summary_path, "w") as f:
        json.dump(summary, f, indent=2)

    print("\n" + "═" * 65)
    print("  COMBINED EVALUATION SUMMARY — JobBridge RAG Pipeline")
    print("═" * 65)

    # RAGAS
    ragas = summary["reports"].get("ragas_report", {}).get("summary", {})
    if ragas:
        print("\n  📊 RAGAS (generation quality):")
        metrics = [
            ("Faithfulness",      "faithfulness"),
            ("Answer Relevancy",  "answer_relevancy"),
            ("Context Precision", "context_precision"),
            ("Context Recall",    "context_recall"),
            ("Overall",           "overall"),
        ]
        for label, key in metrics:
            val = ragas.get(key, "N/A")
            bar = "█" * int(val * 20) if isinstance(val, float) else ""
            print(f"    {label:<22} {val:.4f}  {bar}" if isinstance(val, float)
                  else f"    {label:<22} {val}")

    # Retrieval
    ret = summary["reports"].get("retrieval_report", {}).get("results", {})
    if ret:
        print("\n  🔍 Retrieval NDCG@K by stage:")
        for stage in ["bm25", "dense", "rrf", "reranked"]:
            ndcg = ret.get(stage, {}).get("ndcg", "N/A")
            bar  = "█" * int(ndcg * 20) if isinstance(ndcg, float) else ""
            print(f"    {stage:<12} NDCG={ndcg:.4f}  {bar}"
                  if isinstance(ndcg, float) else f"    {stage:<12} {ndcg}")

        rrf_ndcg    = ret.get("rrf", {}).get("ndcg", 0)
        bm25_ndcg   = ret.get("bm25", {}).get("ndcg", 0)
        dense_ndcg  = ret.get("dense", {}).get("ndcg", 0)
        rerank_ndcg = ret.get("reranked", {}).get("ndcg", 0)
        print(f"\n    RRF lift over BM25:    {rrf_ndcg - bm25_ndcg:+.4f}")
        print(f"    RRF lift over Dense:   {rrf_ndcg - dense_ndcg:+.4f}")
        print(f"    Reranker lift over RRF:{rerank_ndcg - rrf_ndcg:+.4f}")

    # Latency
    lat = summary["reports"].get("latency_report", {}).get("stages", {})
    if lat:
        print("\n  ⏱  Latency (mean ms per stage):")
        stage_labels = {
            "query_processing": "Query processing",
            "bm25":             "BM25 retrieval",
            "dense":            "Dense retrieval",
            "rrf":              "RRF fusion",
            "reranking":        "Reranking",
            "context_prompt":   "Context + prompt",
            "generation":       "Generation",
            "total":            "TOTAL",
        }
        for key, label in stage_labels.items():
            data = lat.get(key, {})
            if data:
                mean = data.get("mean_ms", 0)
                p95  = data.get("p95_ms", 0)
                print(f"    {label:<22} mean={mean:>7.0f}ms  p95={p95:>7.0f}ms")

    # Chunking
    chk = summary["reports"].get("chunking_report", {})
    if chk:
        p   = chk.get("pipeline", {})
        cs  = chk.get("chunk_size_distribution", {})
        thr = chk.get("throughput", {})
        print("\n  📄 Chunking:")
        print(f"    Total chunks:      {p.get('total_chunks', 'N/A')}")
        print(f"    Sources indexed:   {chk.get('chunks_per_document', {}).get('total_sources', 'N/A')}")
        print(f"    Mean chunk size:   {cs.get('mean_chars', 'N/A')} chars")
        print(f"    Noise filtered:    {p.get('noise_filter_rate', 0)*100:.1f}%")
        print(f"    Throughput:        {thr.get('chunks_per_second', 'N/A')} chunks/sec")

    print("\n" + "═" * 65)
    print(f"  Full summary saved to {summary_path}")
    print("═" * 65)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--skip-ragas",     action="store_true")
    parser.add_argument("--skip-retrieval", action="store_true")
    parser.add_argument("--skip-latency",   action="store_true")
    parser.add_argument("--skip-chunking",  action="store_true")
    parser.add_argument("--data-dir",       type=str, default="data/raw")
    parser.add_argument("--k",              type=int, default=5)
    parser.add_argument("--queries",        type=int, default=5)
    args = parser.parse_args()

    RESULTS_DIR.mkdir(parents=True, exist_ok=True)
    results = {}

    if not args.skip_chunking:
        results["chunking"] = run("chunking_metrics.py", [args.data_dir])

    if not args.skip_latency:
        results["latency"] = run("latency_profiler.py",
                                 ["--queries", str(args.queries)])

    if not args.skip_retrieval:
        results["retrieval"] = run("retrieval_metrics.py",
                                   ["--k", str(args.k)])

    if not args.skip_ragas:
        results["ragas"] = run("evaluate_ragas.py")

    summarize()

    failed = [k for k, v in results.items() if not v]
    if failed:
        print(f"\n  ⚠️  These scripts had errors: {', '.join(failed)}")
        print("  Check that the RAG server is running and documents are ingested.")


if __name__ == "__main__":
    main()
