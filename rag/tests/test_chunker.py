"""Tests for recursive chunker."""

import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from ingestion.loader import RawDocument
from ingestion.chunker import chunk_document, CHUNK_SIZE


def test_short_doc_is_single_chunk():
    doc = RawDocument("Hello world.", source="test.txt")
    chunks = chunk_document(doc)
    assert len(chunks) == 1
    assert chunks[0].text == "Hello world."


def test_long_doc_is_split():
    long_text = ("This is a sentence. " * 100).strip()
    doc = RawDocument(long_text, source="test.txt")
    chunks = chunk_document(doc)
    assert len(chunks) > 1
    for chunk in chunks:
        # Each chunk must be at most CHUNK_SIZE + overlap buffer
        assert len(chunk.text) <= CHUNK_SIZE * 1.5


def test_chunk_indices_are_sequential():
    text = "\n\n".join([f"Paragraph {i}. " * 20 for i in range(10)])
    doc = RawDocument(text, source="test.txt")
    chunks = chunk_document(doc)
    for i, chunk in enumerate(chunks):
        assert chunk.chunk_index == i


def test_source_preserved():
    doc = RawDocument("Some content here.", source="my_file.pdf", page=3)
    chunks = chunk_document(doc)
    for chunk in chunks:
        assert chunk.source == "my_file.pdf"
        assert chunk.page == 3


if __name__ == "__main__":
    test_short_doc_is_single_chunk()
    test_long_doc_is_split()
    test_chunk_indices_are_sequential()
    test_source_preserved()
    print("All chunker tests passed.")
