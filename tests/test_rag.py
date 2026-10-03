from pipeline.reasoning.rag import TranscriptIndex, _terms


def segments():
    return [{"text": t, "interval": {"start_ms": i * 10_000, "end_ms": (i + 1) * 10_000}}
            for i, t in enumerate(["This starts a lesson.", "Ontology connects concepts and relationships.",
                                   "Metadata describes files and columns.", "Subscribe for future lessons."])]


def test_semantic_paraphrase_retrieval_without_lexical_match():
    ix = TranscriptIndex(segments(), window=1, semantic_scorer=lambda q, p: [0.1, 0.95, 0.2, 0.1])
    hits = ix.search("How are entities interconnected?", k=1)
    assert hits[0]["start_ms"] == 10_000
    assert hits[0]["retrieval_method"] == "hybrid_e5_bm25"


def test_encoder_failure_preserves_lexical_and_reports_fallback():
    def broken(*args):
        raise RuntimeError("private details")
    ix = TranscriptIndex(segments(), window=1, semantic_scorer=broken)
    hit = ix.search("metadata", k=1)[0]
    assert hit["start_ms"] == 20_000
    assert hit["retrieval_method"] == "lexical_bm25"
    assert "private" not in hit["retrieval_warning"]


def test_no_overlap_empty_zero_and_multilingual_tokens():
    assert TranscriptIndex([]).search("anything") == []
    assert TranscriptIndex(segments()).search("lesson", k=0) == []
    assert "ज्ञान" in _terms("ज्ञान के संबंध")
    hits = TranscriptIndex(segments(), window=2).search("lesson metadata subscribe", k=10)
    assert all(a["end_ms"] <= b["start_ms"] for a, b in zip(hits, hits[1:]))


def test_bad_dense_shape_and_nan_fall_back():
    for scores in ([0.1], [float("nan")] * 4):
        ix = TranscriptIndex(segments(), window=1, semantic_scorer=lambda q, p: scores)
        assert ix.search("metadata", k=1)[0]["retrieval_method"] == "lexical_bm25"
