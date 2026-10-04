# ═══════════════════════════════════════════════════════════════
# tests / test_rag_chunking.py
#
# PURPOSE: RAG chunking + term helpers (no DB / network needed).
# ═══════════════════════════════════════════════════════════════

import pytest

from src.domains.chatbot.rag_service import chunk_text, _terms, _query_terms


def test_short_text_is_single_chunk():
    assert chunk_text("hello world") == ["hello world"]


def test_empty_text_gives_no_chunks():
    assert chunk_text("   \n ") == []


def test_long_text_splits_with_overlap():
    text = " ".join(f"Sentence number {i} is here." for i in range(200))
    chunks = chunk_text(text, chunk_size=300, overlap=50)
    assert len(chunks) > 1
    assert all(len(c) <= 300 for c in chunks)
    # Overlap: next chunk starts with text that was in the previous one
    assert chunks[1][:20] in chunks[0]


def test_terminates_when_no_break_points():
    chunks = chunk_text("x" * 5000, chunk_size=1000, overlap=200)
    assert len(chunks) >= 5
    assert "".join(c[:800] for c in chunks[:-1]).count("x") > 0


def test_overlap_must_be_smaller_than_chunk_size():
    with pytest.raises(ValueError):
        chunk_text("abc", chunk_size=100, overlap=100)


def test_query_terms_drop_stopwords():
    assert _query_terms("How long does shipping take?") == {"long", "shipping", "take"}


def test_query_terms_keep_all_if_only_stopwords():
    assert _query_terms("what is the") == {"what", "is", "the"}


def test_terms_ignores_case_and_punctuation():
    assert _terms("Refund Policy, please!") == {"refund", "policy", "please"}
