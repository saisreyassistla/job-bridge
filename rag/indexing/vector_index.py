"""Stage 5B — Dense embeddings using sentence-transformers + Qdrant."""

from __future__ import annotations
import os
import uuid
from tqdm import tqdm
from sentence_transformers import SentenceTransformer
from qdrant_client import QdrantClient
from qdrant_client.models import Distance, VectorParams, PointStruct
from ingestion.chunker import Chunk

QDRANT_URL     = os.getenv("QDRANT_URL", "http://localhost:6333")
QDRANT_API_KEY = os.getenv("QDRANT_API_KEY")
COLLECTION     = os.getenv("QDRANT_COLLECTION", "hybrid_rag")
DENSE_TOP_K    = int(os.getenv("DENSE_TOP_K", "30"))
EMBEDDING_DIM  = 384
BATCH_SIZE     = 50

_embedder = SentenceTransformer("all-MiniLM-L6-v2")


def _embed(texts: list) -> list:
    return _embedder.encode(texts, show_progress_bar=False, convert_to_numpy=True).tolist()


def _embed_query(text: str) -> list:
    return _embedder.encode([text], show_progress_bar=False, convert_to_numpy=True)[0].tolist()


class VectorIndex:
    def __init__(self):
        self.client = QdrantClient(
            url=QDRANT_URL,
            api_key=QDRANT_API_KEY or None,
            check_compatibility=False,
        )
        self._ensure_collection()

    def _ensure_collection(self):
        existing = [c.name for c in self.client.get_collections().collections]
        if COLLECTION not in existing:
            self.client.create_collection(
                collection_name=COLLECTION,
                vectors_config=VectorParams(size=EMBEDDING_DIM, distance=Distance.COSINE)
            )

    def upsert(self, chunks: list) -> None:
        for i in tqdm(range(0, len(chunks), BATCH_SIZE), desc="Upserting vectors"):
            batch      = chunks[i : i + BATCH_SIZE]
            texts      = [c.text for c in batch]
            embeddings = _embed(texts)
            points = [
                PointStruct(
                    id=str(uuid.uuid4()),
                    vector=emb,
                    payload={
                        "text":        chunk.text,
                        "source":      chunk.source,
                        "page":        chunk.page,
                        "chunk_index": chunk.chunk_index,
                        **chunk.metadata,
                    }
                )
                for chunk, emb in zip(batch, embeddings)
            ]
            self.client.upsert(collection_name=COLLECTION, points=points)

    def search(self, query: str, top_k: int = DENSE_TOP_K) -> list:
        query_vector = _embed_query(query)
        try:
            results = self.client.query_points(
                collection_name=COLLECTION,
                query=query_vector,
                limit=top_k,
                with_payload=True
            ).points
        except Exception:
            results = self.client.search(
                collection_name=COLLECTION,
                query_vector=query_vector,
                limit=top_k,
                with_payload=True
            )
        chunks_with_scores = []
        for hit in results:
            p = hit.payload
            chunk = Chunk(
                text=p.get("text", ""),
                source=p.get("source", ""),
                page=p.get("page", 0),
                chunk_index=p.get("chunk_index", 0),
                metadata={k: v for k, v in p.items() if k != "text"}
            )
            chunks_with_scores.append((chunk, hit.score))
        return chunks_with_scores
