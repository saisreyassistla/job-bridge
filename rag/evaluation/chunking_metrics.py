"""
Chunking & ingestion metrics — reports chunk size distribution,
overlap ratio, noise filter rate, deduplication rate, and throughput.

Usage:
  python evaluation/chunking_metrics.py ./data/raw
  python evaluation/chunking_metrics.py ./data/raw --output evaluation/results/chunking_report.json
"""

from __future__ import annotations
import os
import sys
import json
import time
import argparse
import statistics
from pathlib import Path
from datetime import datetime

sys.path.insert(0, str(Path(__file__).parent.parent))
from dotenv import load_dotenv
load_dotenv()

from ingestion.loader import load_directory
from ingestion.cleaner import clean_documents
from ingestion.chunker import chunk_documents, CHUNK_SIZE, CHUNK_OVERLAP
from ingestion.enricher import enrich


def analyze(directory: str) -> dict:
    print(f"\nAnalyzing ingestion pipeline on: {directory}")

    t0       = time.perf_counter()
    raw_docs = list(load_directory(directory))
    t1       = time.perf_counter()
    print(f"  Stage 1 — Loaded:    {len(raw_docs)} raw pages/sections")

    cleaned  = clean_documents(raw_docs)
    t2       = time.perf_counter()
    noise_filtered = len(raw_docs) - len(cleaned)
    print(f"  Stage 2 — Cleaned:   {len(cleaned)} docs  "
          f"({noise_filtered} filtered)")

    chunks   = chunk_documents(cleaned)
    t3       = time.perf_counter()
    print(f"  Stage 3 — Chunked:   {len(chunks)} chunks")

    enriched = enrich(chunks)
    t4       = time.perf_counter()
    print(f"  Stage 4 — Enriched:  {len(enriched)} chunks")

    # Chunk size distribution
    char_counts = [len(c.text) for c in enriched]
    word_counts = [c.metadata.get("word_count", 0) for c in enriched]

    # Overlap ratio
    overlap_ratio = CHUNK_OVERLAP / CHUNK_SIZE if CHUNK_SIZE > 0 else 0

    # Chunks per document
    source_counts: dict = {}
    for c in enriched:
        source_counts[c.source] = source_counts.get(c.source, 0) + 1
    chunks_per_doc = list(source_counts.values())

    total_time = t4 - t0
    throughput  = len(enriched) / total_time if total_time > 0 else 0

    return {
        "timestamp":  datetime.now().isoformat(),
        "directory":  directory,
        "config": {
            "chunk_size":    CHUNK_SIZE,
            "chunk_overlap": CHUNK_OVERLAP,
            "overlap_ratio": round(overlap_ratio, 3),
        },
        "pipeline": {
            "raw_docs":          len(raw_docs),
            "after_cleaning":    len(cleaned),
            "noise_filtered":    noise_filtered,
            "noise_filter_rate": round(noise_filtered / len(raw_docs), 4)
                                  if raw_docs else 0,
            "total_chunks":      len(enriched),
        },
        "chunk_size_distribution": {
            "mean_chars":   round(statistics.mean(char_counts), 1)   if char_counts else 0,
            "median_chars": round(statistics.median(char_counts), 1) if char_counts else 0,
            "min_chars":    min(char_counts)  if char_counts else 0,
            "max_chars":    max(char_counts)  if char_counts else 0,
            "stdev_chars":  round(statistics.stdev(char_counts), 1)
                            if len(char_counts) > 1 else 0,
            "mean_words":   round(statistics.mean(word_counts), 1)   if word_counts else 0,
        },
        "chunks_per_document": {
            "mean":          round(statistics.mean(chunks_per_doc), 1)   if chunks_per_doc else 0,
            "median":        round(statistics.median(chunks_per_doc), 1) if chunks_per_doc else 0,
            "min":           min(chunks_per_doc)  if chunks_per_doc else 0,
            "max":           max(chunks_per_doc)  if chunks_per_doc else 0,
            "total_sources": len(source_counts),
        },
        "latency_ms": {
            "stage_1_load":    round((t1 - t0) * 1000, 2),
            "stage_2_clean":   round((t2 - t1) * 1000, 2),
            "stage_3_chunk":   round((t3 - t2) * 1000, 2),
            "stage_4_enrich":  round((t4 - t3) * 1000, 2),
            "total_ingestion": round((t4 - t0) * 1000, 2),
        },
        "throughput": {
            "chunks_per_second": round(throughput, 1),
        },
    }


def print_report(r: dict):
    p   = r["pipeline"]
    cs  = r["chunk_size_distribution"]
    cp  = r["chunks_per_document"]
    lt  = r["latency_ms"]
    cfg = r["config"]

    print("\n" + "═" * 60)
    print("  CHUNKING & INGESTION METRICS — JobBridge RAG Pipeline")
    print("═" * 60)
    print(f"  Directory:          {r['directory']}")
    print(f"  Chunk size:         {cfg['chunk_size']} chars  "
          f"(overlap: {cfg['chunk_overlap']} = {cfg['overlap_ratio']*100:.0f}%)")
    print("─" * 60)
    print(f"  Raw pages loaded:   {p['raw_docs']}")
    print(f"  After cleaning:     {p['after_cleaning']}  "
          f"({p['noise_filter_rate']*100:.1f}% filtered)")
    print(f"  Total chunks:       {p['total_chunks']}")
    print(f"  Sources indexed:    {cp['total_sources']}")
    print("─" * 60)
    print("  Chunk size distribution (chars):")
    print(f"    Mean:    {cs['mean_chars']}    Median: {cs['median_chars']}")
    print(f"    Min:     {cs['min_chars']}     Max:    {cs['max_chars']}"
          f"    StDev:  {cs['stdev_chars']}")
    print(f"    Avg words/chunk:  {cs['mean_words']}")
    print("─" * 60)
    print("  Chunks per document:")
    print(f"    Mean: {cp['mean']}    Median: {cp['median']}"
          f"    Min: {cp['min']}    Max: {cp['max']}")
    print("─" * 60)
    print("  Stage latencies:")
    print(f"    Stage 1 (load):    {lt['stage_1_load']}ms")
    print(f"    Stage 2 (clean):   {lt['stage_2_clean']}ms")
    print(f"    Stage 3 (chunk):   {lt['stage_3_chunk']}ms")
    print(f"    Stage 4 (enrich):  {lt['stage_4_enrich']}ms")
    print(f"    Total ingestion:   {lt['total_ingestion']}ms")
    print(f"  Throughput:  {r['throughput']['chunks_per_second']} chunks/sec")
    print("═" * 60)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("directory", nargs="?", default="data/raw")
    parser.add_argument("--output", type=str,
                        default="evaluation/results/chunking_report.json")
    args = parser.parse_args()

    report = analyze(args.directory)
    print_report(report)

    Path(args.output).parent.mkdir(parents=True, exist_ok=True)
    with open(args.output, "w") as f:
        json.dump(report, f, indent=2)
    print(f"\n  Report saved to {args.output}")


if __name__ == "__main__":
    main()
