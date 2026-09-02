"""
Latency profiler — instruments every stage of the RAG pipeline and
produces a breakdown of time spent per stage, per query.

Usage:
  python evaluation/latency_profiler.py
  python evaluation/latency_profiler.py --queries 10
  python evaluation/latency_profiler.py --output evaluation/results/latency_report.json
"""

from __future__ import annotations
import os
import sys
import json
import time
import argparse
import statistics
import requests
from pathlib import Path
from datetime import datetime

sys.path.insert(0, str(Path(__file__).parent.parent))
from dotenv import load_dotenv
load_dotenv(Path(__file__).resolve().parents[2] / ".env", override=True)

RAG_URL = os.getenv("RAG_SERVER_URL", "http://localhost:8000")
SERVICE_API_KEY = os.getenv("SERVICE_API_KEY", "")

TEST_QUERIES = [
    "What are Amazon's leadership principles?",
    "How should I prepare for a behavioral interview at Amazon?",
    "What is the STAR method for interviews?",
    "What is customer obsession at Amazon?",
    "How does Amazon use leadership principles in hiring?",
    "What questions does Amazon ask about ownership?",
    "What is bias for action at Amazon?",
    "How do I prepare for an Amazon software engineer interview?",
    "What functional competencies does Amazon evaluate?",
    "What is earn trust at Amazon?",
]

STAGE_LABELS = {
    "query_processing":  "Stage 6  — Query processing (rewrite + HyDE)",
    "bm25":              "Stage 5A — BM25 retrieval",
    "dense":             "Stage 5B — Dense retrieval (embeddings + Qdrant)",
    "rrf":               "Stage 7  — Reciprocal rank fusion",
    "reranking":         "Stage 8  — Reranking (cross-encoder)",
    "context_prompt":    "Stage 9  — Context optimization + prompt build",
    "generation":        "Stage 10 — Claude generation",
    "total":             "Total    — End-to-end pipeline",
}


def run_http_pipeline(question: str) -> dict:
    """Call /report endpoint and extract per-stage latency."""
    t0 = time.perf_counter() * 1000
    r  = requests.post(f"{RAG_URL}/report",
                       headers={"x-service-key": SERVICE_API_KEY},
                       json={"question": question}, timeout=120)
    r.raise_for_status()
    total_ms = (time.perf_counter() * 1000) - t0

    data    = r.json()
    latency = data.get("latency_ms", {})
    latency["total"] = round(total_ms, 1)
    return latency


def print_latency_report(timings: dict, n_queries: int):
    print("\n" + "═" * 72)
    print("  LATENCY PROFILER REPORT — JobBridge RAG Pipeline")
    print("═" * 72)
    print(f"  Queries run: {n_queries}    "
          f"Timestamp: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print("─" * 72)
    print(f"  {'Stage':<48} {'Mean':>8} {'P50':>8} {'P95':>8} {'Max':>8}")
    print(f"  {'─'*48} {'─'*8} {'─'*8} {'─'*8} {'─'*8}")

    for key, label in STAGE_LABELS.items():
        vals = timings.get(key, [])
        if not vals:
            continue
        mean = statistics.mean(vals)
        p50  = statistics.median(vals)
        p95  = sorted(vals)[max(0, int(len(vals) * 0.95) - 1)]
        mx   = max(vals)
        print(f"  {label:<48} {mean:>7.0f}ms {p50:>7.0f}ms "
              f"{p95:>7.0f}ms {mx:>7.0f}ms")

    print("─" * 72)

    # Bottleneck
    stage_means = {k: statistics.mean(v)
                   for k, v in timings.items()
                   if v and k != "total"}
    if stage_means:
        bottleneck = max(stage_means, key=stage_means.get)
        total_mean = sum(stage_means.values())
        pct = (stage_means[bottleneck] / total_mean * 100) if total_mean else 0
        print(f"\n  ⚠️  Bottleneck: {STAGE_LABELS.get(bottleneck, bottleneck)}")
        print(f"     Mean: {stage_means[bottleneck]:.0f}ms  ({pct:.0f}% of total)")
    print("═" * 72)


def save_latency_report(timings: dict, n_queries: int, output_path: str):
    Path(output_path).parent.mkdir(parents=True, exist_ok=True)
    report = {
        "timestamp": datetime.now().isoformat(),
        "n_queries":  n_queries,
        "stages": {
            key: {
                "mean_ms":   round(statistics.mean(vals), 2),
                "median_ms": round(statistics.median(vals), 2),
                "p95_ms":    round(sorted(vals)[max(0, int(len(vals)*0.95)-1)], 2),
                "max_ms":    round(max(vals), 2),
                "min_ms":    round(min(vals), 2),
                "all_ms":    vals,
            }
            for key, vals in timings.items() if vals
        }
    }
    with open(output_path, "w") as f:
        json.dump(report, f, indent=2)
    print(f"\n  Report saved to {output_path}")


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--queries", type=int, default=5)
    parser.add_argument("--output",  type=str,
                        default="evaluation/results/latency_report.json")
    args = parser.parse_args()

    queries = TEST_QUERIES[:args.queries]
    timings: dict[str, list[float]] = {k: [] for k in STAGE_LABELS}

    # Check server
    try:
        r = requests.get(f"{RAG_URL}/health", timeout=5)
        print(f"RAG server OK — {r.json().get('indexed_chunks','?')} chunks indexed")
    except Exception:
        print("❌ RAG server not reachable.")
        sys.exit(1)

    print(f"\nProfiling {len(queries)} queries...")
    for i, q in enumerate(queries, 1):
        print(f"  [{i}/{len(queries)}] {q[:65]}...")
        try:
            latency = run_http_pipeline(q)
            for key in STAGE_LABELS:
                if key in latency:
                    timings[key].append(latency[key])
        except Exception as e:
            print(f"    ⚠️  Failed: {e}")

    # Remove empty
    timings = {k: v for k, v in timings.items() if v}

    print_latency_report(timings, len(queries))
    save_latency_report(timings, len(queries), args.output)


if __name__ == "__main__":
    main()
