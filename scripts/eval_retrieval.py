#!/usr/bin/env python3
"""Measure retrieval on its own: hit@k, recall@k, MRR and context size.

    PYTHONNOUSERSITE=1 python scripts/eval_retrieval.py
    PYTHONNOUSERSITE=1 python scripts/eval_retrieval.py --diversity 0.0 0.35 0.5

Why: end-to-end EX cannot tell whether retrieval surfaced the right chunk.
This script scores `dense` (no MMR) and `MMR` at several `top_k` values against
weak labels derived from the golden SQL. Use it to choose `top_k` and to decide
whether the KB needs more/smaller chunks.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

import faiss

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT))

from app.chatbot.nl2sql import NL2SQLChatbot  # noqa: E402
from app.eval.paths import EvalPaths  # noqa: E402
from app.eval.retrieval import evidence_for, score_retrieval  # noqa: E402
from app.models.eval import EvalCase  # noqa: E402


def load_cases(path: Path) -> list[EvalCase]:
    return [
        EvalCase.model_validate_json(line)
        for line in path.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]


def chunk_id(metadata: dict) -> tuple[str, int]:
    return metadata["source"], metadata["index"]


def dense(kb, doc_processor, query: str, k: int) -> list[dict]:
    embedding = (
        doc_processor.embedding_model.encode([query])[0]
        .reshape(1, -1)
        .astype("float32")
    )
    faiss.normalize_L2(embedding)
    _, indices = kb.index.search(embedding, k)
    return [
        {"text": kb.chunks[idx], "metadata": kb.chunk_metadata[idx]}
        for idx in indices[0]
        if 0 <= idx < len(kb.chunks)
    ]


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--diversity",
        nargs="+",
        type=float,
        default=[0.0, 0.2, 0.35, 0.5],
        help="MMR redundancy weights (0 = pure relevance)",
    )
    args = parser.parse_args()

    chatbot = NL2SQLChatbot()
    kb = chatbot.knowledge_base
    cases = [
        case
        for case in load_cases(EvalPaths.default().dataset)
        if case.required_behavior == "answer"
    ]

    chunks = [
        (chunk_id(metadata), text)
        for text, metadata in zip(kb.chunks, kb.chunk_metadata)
    ]
    print(f"chunks: {len(chunks)}  cases: {len(cases)}")

    labels: dict[str, set[tuple[str, int]]] = {}
    unlabeled = 0
    for case in cases:
        # Specific values first; generic column names only as a fallback.
        evidence = evidence_for(case, include_columns=False)
        relevant = {
            cid for cid, text in chunks if any(item in text.lower() for item in evidence)
        }
        if not relevant:
            evidence = evidence_for(case, include_columns=True)
            relevant = {
                cid
                for cid, text in chunks
                if any(item in text.lower() for item in evidence)
            }

        if relevant:
            labels[case.id] = relevant
        else:
            unlabeled += 1

    print(f"labeled: {len(labels)}  unlabeled: {unlabeled}\n")

    strategies: list[tuple[str, float | None]] = [("dense", None)]
    strategies += [("mmr", value) for value in args.diversity]

    for name, diversity in strategies:
        for k in range(1, len(chunks) + 1):
            hits: list[bool] = []
            recalls: list[float] = []
            rrs: list[float] = []
            chars: list[int] = []

            for case in cases:
                if case.id not in labels:
                    continue

                if name == "dense":
                    results = dense(kb, chatbot.doc_processor, case.question, k)
                else:
                    results = kb.retrieve_with_mmr(
                        case.question,
                        chatbot.doc_processor,
                        top_k=k,
                        diversity=diversity,
                    )

                retrieved = [chunk_id(result["metadata"]) for result in results]
                score = score_retrieval(retrieved, labels[case.id])
                if score is None:
                    continue

                hits.append(score.hit)
                recalls.append(score.recall)
                rrs.append(score.reciprocal_rank)
                chars.append(sum(len(result["text"]) for result in results))

            total = len(hits)
            label = "dense" if name == "dense" else f"mmr d={diversity:g}"
            print(
                f"{label:12} k={k}  hit@k={sum(hits) / total:.1%}  "
                f"recall@k={sum(recalls) / total:.3f}  "
                f"mrr={sum(rrs) / total:.3f}  "
                f"avg_chars={sum(chars) / total:.0f}"
            )
        print()


if __name__ == "__main__":
    main()
