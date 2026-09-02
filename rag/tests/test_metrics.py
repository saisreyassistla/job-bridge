"""Tests for source-level retrieval metrics."""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from evaluation.retrieval_metrics import recall_at_k


def test_recall_deduplicates_source_aliases():
    chunks = [{"source": "Interview_Questions_Bank_amz.pdf"}]
    aliases = [
        "Interview_Questions_Bank_amz.pdf",
        "./data/raw/Interview_Questions_Bank_amz.pdf",
        "data/raw/Interview_Questions_Bank_amz.pdf",
    ]

    assert recall_at_k(chunks, aliases, 1) == 1.0


def test_recall_does_not_count_unrelated_sources():
    chunks = [{"source": "other.pdf"}]

    assert recall_at_k(chunks, ["target.pdf"], 1) == 0.0


if __name__ == "__main__":
    test_recall_deduplicates_source_aliases()
    test_recall_does_not_count_unrelated_sources()
    print("All retrieval metric tests passed.")