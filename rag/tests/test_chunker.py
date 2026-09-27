"""Basic tests for RAG pipeline components."""

import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

def test_chunker_splits_long_text():
    from ingestion.chunker import chunk_documents
    from ingestion.loader import RawDocument

    long_text = "A" * 600
    docs = [RawDocument(
        content=long_text,
        source="test.txt",
        page=0
    )]
    chunks = chunk_documents(docs)
    assert len(chunks) > 1

def test_chunker_respects_size():
    from ingestion.chunker import chunk_documents
    from ingestion.loader import RawDocument

    docs = [RawDocument(
        content="Hello world. " * 100,
        source="test.txt",
        page=0
    )]
    chunks = chunk_documents(docs)
    for chunk in chunks:
        assert len(chunk.text) <= 577  # 512 + 64 overlap + buffer

def test_rrf_ranks_correctly():
    from retrieval.rrf import reciprocal_rank_fusion

    class MockChunk:
        def __init__(self, id):
            self.source   = f"doc_{id}"
            self.chunk_index = id
            self.text     = f"chunk {id}"
            self.page     = 0
            self.section  = ""
            self.word_count = 2

    chunk1 = MockChunk(1)
    chunk2 = MockChunk(2)

    bm25  = [(chunk1, 0.9), (chunk2, 0.7)]
    dense = [(chunk2, 0.8), (chunk1, 0.6)]

    result = reciprocal_rank_fusion(bm25, dense)

    assert len(result) > 0
    # chunk2 appears in both lists — should rank highest
    top_chunk, top_score = result[0]
    assert top_chunk.source == chunk2.source

def test_cleaner_deduplicates():
    from ingestion.cleaner import clean_documents
    from ingestion.loader import RawDocument

    duplicate_text = "This is duplicate content."
    docs = [
        RawDocument(content=duplicate_text, source="a.txt", page=0),
        RawDocument(content=duplicate_text, source="b.txt", page=0),
    ]
    cleaned = list(clean_documents(docs))
    assert len(cleaned) == 1  # duplicate removed

def test_cleaner_filters_noise():
    from ingestion.cleaner import clean_documents
    from ingestion.loader import RawDocument

    noisy = RawDocument(
        content="123456789!@#$%^&*()",  # no alphabetic chars
        source="noise.txt",
        page=0
    )
    cleaned = list(clean_documents([noisy]))
    assert len(cleaned) == 0  # noise filtered
