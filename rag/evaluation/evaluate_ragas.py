"""
RAGAS evaluation script for the JobBridge Hybrid RAG pipeline.

Uses Claude (Anthropic) as the judge model instead of Gemini
to avoid Python 3.9 / google-generativeai compatibility issues.

Measures:
  - Faithfulness       (is the answer grounded in retrieved chunks?)
  - Answer Relevance   (does the answer address the question?)
  - Context Precision  (are retrieved chunks actually relevant?)
  - Context Recall     (do chunks contain enough info to answer?)

Usage:
  python evaluation/evaluate_ragas.py
  python evaluation/evaluate_ragas.py --dataset evaluation/datasets/jobbridge_eval.json
  python evaluation/evaluate_ragas.py --output evaluation/results/ragas_report.json
"""

from __future__ import annotations
import os
import sys
import json
import argparse
import requests
from pathlib import Path
from datetime import datetime
from typing import Optional

sys.path.insert(0, str(Path(__file__).parent.parent))
from dotenv import load_dotenv
load_dotenv(Path(__file__).resolve().parents[2] / ".env", override=True)

import anthropic

_client = anthropic.Anthropic(api_key=os.getenv("ANTHROPIC_API_KEY"))
RAG_URL = os.getenv("RAG_SERVER_URL", "http://localhost:8000")
SERVICE_API_KEY = os.getenv("SERVICE_API_KEY", "")
RAG_HEADERS = {"x-service-key": SERVICE_API_KEY}

# ── Evaluation dataset ────────────────────────────────────────────────────────
# Grounded in the Amazon Interview Questions Bank PDF you ingested.
# ground_truth = what a correct answer should contain.

DEFAULT_EVAL_DATASET = [
    {
        "question": "What are Amazon's leadership principles?",
        "ground_truth": "Amazon has 16 leadership principles including Customer Obsession, Ownership, Invent and Simplify, Are Right A Lot, Learn and Be Curious, Hire and Develop the Best, Insist on the Highest Standards, Think Big, Bias for Action, Frugality, Earn Trust, Dive Deep, Have Backbone Disagree and Commit, Deliver Results, Strive to be Earth's Best Employer, and Success and Scale Bring Broad Responsibility.",
    },
    {
        "question": "How should I use the Amazon Interview Questions Bank?",
        "ground_truth": "Select a Leadership Principle or Functional Competency, assign it to an interviewer, use the provided questions to assess candidates during the interview process following the Making Great Hiring Decisions course methodology.",
    },
    {
        "question": "What is the STAR method for interviews?",
        "ground_truth": "STAR stands for Situation Task Action Result. It is a structured method for answering behavioral interview questions by describing the situation, the task you needed to accomplish, the action you took, and the result you achieved.",
    },
    {
        "question": "What types of questions does Amazon ask in a software engineer interview?",
        "ground_truth": "Amazon asks coding questions on data structures and algorithms, system design questions, and behavioral questions based on their 16 leadership principles framed as Tell me about a time when.",
    },
    {
        "question": "How do I prepare for a behavioral interview at Amazon?",
        "ground_truth": "Use the STAR method to structure answers. Prepare stories from past experience that demonstrate each leadership principle. Hiring managers assign 1 to 2 leadership principles to each interviewer to assess.",
    },
    {
        "question": "What is customer obsession at Amazon?",
        "ground_truth": "Customer Obsession is Amazon's first leadership principle. Leaders start with the customer and work backwards. They work vigorously to earn and keep customer trust. Although leaders pay attention to competitors they obsess over customers.",
    },
    {
        "question": "What is bias for action at Amazon?",
        "ground_truth": "Bias for Action means speed matters in business. Many decisions and actions are reversible and do not need extensive study. Amazon values calculated risk taking and moving fast even with incomplete information.",
    },
    {
        "question": "What functional competencies does the Amazon interview questions bank cover?",
        "ground_truth": "The Amazon Interview Questions Bank covers functional competencies including strategic thinking communication inclusion data driven decision making and other leadership and management skills in addition to the 16 leadership principles.",
    },
]


# ── Stage 1: Run pipeline on each question ────────────────────────────────────

def run_pipeline_on_dataset(dataset: list[dict]) -> list[dict]:
    """Call the RAG server for each question and collect answer + contexts."""
    results = []
    print(f"\nRunning pipeline on {len(dataset)} questions...")

    for i, item in enumerate(dataset, 1):
        question = item["question"]
        print(f"  [{i}/{len(dataset)}] {question[:65]}...")

        try:
            # Use /report endpoint to get full chunk context
            r = requests.post(
                f"{RAG_URL}/report",
                headers=RAG_HEADERS,
                json={"question": question},
                timeout=90,
            )
            r.raise_for_status()
            data = r.json()

            answer   = data.get("answer", "")
            # Get full chunk texts from reranked stage (top 5)
            reranked = data.get("stages", {}).get("reranked", [])
            contexts = [c.get("text", "") for c in reranked if c.get("text")]

            if not contexts:
                # Fallback to /query endpoint
                r2 = requests.post(
                    f"{RAG_URL}/query",
                    headers=RAG_HEADERS,
                    json={"question": question},
                    timeout=60,
                )
                r2.raise_for_status()
                data2    = r2.json()
                answer   = data2.get("answer", "")
                citations = data2.get("citations", [])
                contexts = [c.get("text_preview", "") for c in citations]

            if not contexts:
                contexts = ["No context retrieved"]

        except Exception as e:
            print(f"    ⚠️  Pipeline call failed: {e}")
            answer   = ""
            contexts = ["Pipeline unavailable"]

        results.append({
            "question":     question,
            "answer":       answer,
            "contexts":     contexts,
            "ground_truth": item.get("ground_truth", ""),
        })

    return results


# ── Stage 2: Claude-based metric scorers ─────────────────────────────────────

def _claude_score(prompt: str) -> float:
    """Call Claude and extract a 0.0–1.0 score from the response."""
    try:
        response = _client.messages.create(
            model="claude-haiku-4-5-20251001",
            max_tokens=128,
            messages=[{"role": "user", "content": prompt}]
        )
        text = response.content[0].text.strip()
        # Extract first float found in response
        import re
        matches = re.findall(r"\d+\.?\d*", text)
        if matches:
            score = float(matches[0])
            return min(max(score, 0.0), 1.0)
        return 0.5
    except Exception as e:
        print(f"    ⚠️  Claude scoring failed: {e}")
        return 0.5


def score_faithfulness(answer: str, contexts: list[str]) -> float:
    """
    Faithfulness: Is every claim in the answer supported by the contexts?
    Score 1.0 = fully grounded, 0.0 = hallucinated.
    """
    context_text = "\n\n".join(contexts[:5])
    prompt = f"""You are evaluating whether an AI answer is faithful to its source context.

CONTEXT (retrieved document chunks):
{context_text}

ANSWER:
{answer}

Task: What fraction of claims in the ANSWER are directly supported by the CONTEXT?
- Score 1.0 if every claim is supported
- Score 0.0 if no claims are supported
- Score between 0 and 1 based on the fraction supported

Reply with ONLY a decimal number between 0.0 and 1.0. Example: 0.85"""
    return _claude_score(prompt)


def score_answer_relevancy(question: str, answer: str) -> float:
    """
    Answer Relevancy: Does the answer actually address the question?
    Score 1.0 = perfectly on-topic, 0.0 = completely off-topic.
    """
    prompt = f"""You are evaluating whether an AI answer is relevant to the question asked.

QUESTION: {question}

ANSWER: {answer}

Task: How relevant is the ANSWER to the QUESTION?
- Score 1.0 if the answer directly and completely addresses the question
- Score 0.0 if the answer is completely unrelated to the question
- Score between 0 and 1 based on relevance

Reply with ONLY a decimal number between 0.0 and 1.0. Example: 0.92"""
    return _claude_score(prompt)


def score_context_precision(question: str, contexts: list[str]) -> float:
    """
    Context Precision: Are the retrieved chunks actually relevant to the question?
    Score 1.0 = all chunks are relevant, 0.0 = no chunks are relevant.
    """
    if not contexts:
        return 0.0
    relevant = 0
    for ctx in contexts:
        prompt = f"""Is the following document chunk relevant to answering this question?

QUESTION: {question}

CHUNK: {ctx[:500]}

Reply with ONLY 1 (relevant) or 0 (not relevant)."""
        score = _claude_score(prompt)
        relevant += 1 if score >= 0.5 else 0
    return relevant / len(contexts)


def score_context_recall(ground_truth: str, contexts: list[str]) -> float:
    """
    Context Recall: Do the retrieved chunks contain enough information
    to support the ground truth answer?
    Score 1.0 = contexts fully support ground truth, 0.0 = no support.
    """
    context_text = "\n\n".join(contexts[:5])
    prompt = f"""You are evaluating whether retrieved document chunks contain
enough information to support a reference answer.

RETRIEVED CHUNKS:
{context_text}

REFERENCE ANSWER (ground truth):
{ground_truth}

Task: What fraction of the information in the REFERENCE ANSWER
can be found in or inferred from the RETRIEVED CHUNKS?
- Score 1.0 if all information is present in the chunks
- Score 0.0 if none of the information is in the chunks

Reply with ONLY a decimal number between 0.0 and 1.0. Example: 0.78"""
    return _claude_score(prompt)


# ── Stage 3: Run all metrics ──────────────────────────────────────────────────

def evaluate_all(results: list[dict]) -> list[dict]:
    """Score every result on all four RAGAS metrics."""
    print("\nScoring with Claude as judge...")
    scored = []

    for i, r in enumerate(results, 1):
        print(f"  [{i}/{len(results)}] Scoring: {r['question'][:55]}...")
        q  = r["question"]
        a  = r["answer"]
        c  = r["contexts"]
        gt = r["ground_truth"]

        faith   = score_faithfulness(a, c)
        rel     = score_answer_relevancy(q, a)
        prec    = score_context_precision(q, c)
        recall  = score_context_recall(gt, c)

        scored.append({
            **r,
            "faithfulness":      round(faith,  4),
            "answer_relevancy":  round(rel,    4),
            "context_precision": round(prec,   4),
            "context_recall":    round(recall, 4),
            "overall":           round((faith + rel + prec + recall) / 4, 4),
        })
        print(f"    faith={faith:.3f}  relevancy={rel:.3f}  precision={prec:.3f}  recall={recall:.3f}")

    return scored


# ── Stage 4: Report ───────────────────────────────────────────────────────────

def print_report(scored: list[dict]):
    def avg(key):
        return sum(r[key] for r in scored) / len(scored)

    faith  = avg("faithfulness")
    rel    = avg("answer_relevancy")
    prec   = avg("context_precision")
    recall = avg("context_recall")
    overall = (faith + rel + prec + recall) / 4

    print("\n" + "═" * 65)
    print("  RAGAS EVALUATION REPORT — JobBridge RAG Pipeline")
    print("  Judge model: claude-haiku-4-5-20251001")
    print("═" * 65)
    print(f"  Evaluated:          {len(scored)} questions")
    print(f"  Timestamp:          {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print("─" * 65)
    print(f"  Faithfulness:       {faith:.4f}   (higher = less hallucination)")
    print(f"  Answer Relevancy:   {rel:.4f}   (higher = more on-topic answers)")
    print(f"  Context Precision:  {prec:.4f}   (higher = less noisy chunks)")
    print(f"  Context Recall:     {recall:.4f}   (higher = chunks cover the answer)")
    print("─" * 65)
    print(f"  Overall avg:        {overall:.4f}")
    print("═" * 65)

    print("\nPer-question breakdown:")
    print(f"  {'Question':<50} {'Faith':>6} {'Relev':>6} {'Prec':>6} {'Rec':>6} {'Avg':>6}")
    print(f"  {'─'*50} {'─'*6} {'─'*6} {'─'*6} {'─'*6} {'─'*6}")
    for r in scored:
        q_short = r["question"][:48] + ".." if len(r["question"]) > 50 else r["question"]
        print(f"  {q_short:<50} {r['faithfulness']:>6.3f} {r['answer_relevancy']:>6.3f} "
              f"{r['context_precision']:>6.3f} {r['context_recall']:>6.3f} {r['overall']:>6.3f}")


def save_report(scored: list[dict], output_path: str):
    def avg(key):
        return round(sum(r[key] for r in scored) / len(scored), 4)

    Path(output_path).parent.mkdir(parents=True, exist_ok=True)
    report = {
        "timestamp":  datetime.now().isoformat(),
        "judge_model": "claude-haiku-4-5-20251001",
        "n_questions": len(scored),
        "summary": {
            "faithfulness":      avg("faithfulness"),
            "answer_relevancy":  avg("answer_relevancy"),
            "context_precision": avg("context_precision"),
            "context_recall":    avg("context_recall"),
            "overall":           avg("overall"),
        },
        "per_question": scored,
    }
    with open(output_path, "w") as f:
        json.dump(report, f, indent=2)
    print(f"\n  Report saved to {output_path}")


# ── Main ──────────────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(description="RAGAS evaluation for JobBridge RAG")
    parser.add_argument("--dataset", type=str, help="Path to JSON eval dataset")
    parser.add_argument("--output",  type=str,
                        default="evaluation/results/ragas_report.json")
    args = parser.parse_args()

    if args.dataset:
        with open(args.dataset) as f:
            dataset = json.load(f)
        print(f"Loaded {len(dataset)} examples from {args.dataset}")
    else:
        dataset = DEFAULT_EVAL_DATASET
        print(f"Using default eval dataset ({len(dataset)} examples)")

    # Check RAG server is up
    try:
        r = requests.get(f"{RAG_URL}/health", timeout=5)
        data = r.json()
        print(f"RAG server OK — {data.get('indexed_chunks', '?')} chunks indexed")
    except Exception:
        print("❌ RAG server not reachable. Start it with: uvicorn api.server:app --port 8000")
        sys.exit(1)

    results = run_pipeline_on_dataset(dataset)
    scored  = evaluate_all(results)
    print_report(scored)
    save_report(scored, args.output)


if __name__ == "__main__":
    main()
