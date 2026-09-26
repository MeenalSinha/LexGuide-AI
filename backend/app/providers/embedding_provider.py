"""
EmbeddingProvider interface + a TF-IDF based implementation.

Production upgrade path: replace TfidfEmbeddingProvider with an
implementation that calls a real embedding model and stores vectors in
pgvector (see docs/architecture.md). The interface is intentionally the
same shape either way, and retrieval is already hybrid (semantic +
keyword overlap + metadata filter) so swapping the backend doesn't change
callers in rag_service.py.
"""
from abc import ABC, abstractmethod
from typing import List, Dict
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.metrics.pairwise import cosine_similarity
import re


class EmbeddingProvider(ABC):
    @abstractmethod
    def retrieve(self, query: str, chunks: List[Dict], top_k: int) -> List[Dict]:
        ...


def _keyword_score(query: str, text: str) -> float:
    q_terms = set(re.findall(r"[a-zA-Z]{3,}", query.lower()))
    if not q_terms:
        return 0.0
    t_terms = set(re.findall(r"[a-zA-Z]{3,}", text.lower()))
    if not t_terms:
        return 0.0
    overlap = len(q_terms & t_terms)
    return overlap / max(len(q_terms), 1)


class TfidfEmbeddingProvider(EmbeddingProvider):
    """
    Hybrid retrieval: TF-IDF cosine similarity (semantic-ish proxy) blended
    with raw keyword overlap (BM25-style proxy), so a single missed synonym
    doesn't zero out a chunk that clearly contains the answer. A second-stage
    reranking pass then reorders the initial candidate set using signals the
    first pass doesn't see (exact phrase match, section-heading relevance),
    the same two-stage retrieve-then-rerank shape a production pgvector +
    cross-encoder pipeline would use (see docs/architecture.md upgrade path).
    """

    def retrieve(self, query: str, chunks: List[Dict], top_k: int) -> List[Dict]:
        if not chunks:
            return []
        texts = [c["text"] for c in chunks]
        try:
            vectorizer = TfidfVectorizer(stop_words="english", max_features=4000)
            matrix = vectorizer.fit_transform(texts + [query])
            sims = cosine_similarity(matrix[-1], matrix[:-1])[0]
        except ValueError:
            sims = [0.0] * len(texts)

        scored = []
        for chunk, sem_score in zip(chunks, sims):
            kw_score = _keyword_score(query, chunk["text"])
            combined = 0.65 * float(sem_score) + 0.35 * kw_score
            scored.append({**chunk, "score": round(combined, 4)})

        scored.sort(key=lambda c: c["score"], reverse=True)
        # Widen the candidate pool before rerank so the second stage has real
        # room to reorder, not just re-confirm the first pass's top-k.
        candidate_pool = scored[:max(top_k * 3, top_k + 5)]
        reranked = self._rerank(query, candidate_pool)
        return reranked[:top_k]

    def _rerank(self, query: str, candidates: List[Dict]) -> List[Dict]:
        """Second-stage rerank: boosts chunks that contain an exact phrase
        match of a multi-word query fragment, or whose section heading
        directly names the query's subject -- signals a pure vector/TF-IDF
        similarity score can miss when phrasing differs from the source."""
        query_lower = query.lower().strip().rstrip("?")
        query_words = [w for w in re.findall(r"[a-zA-Z]{4,}", query_lower)]

        def rerank_score(c: Dict) -> float:
            text_lower = c["text"].lower()
            section_lower = (c.get("section") or "").lower()
            bonus = 0.0
            if query_lower and query_lower in text_lower:
                bonus += 0.25  # near-exact phrase match
            heading_hits = sum(1 for w in query_words if w in section_lower)
            bonus += 0.05 * heading_hits  # section heading names the topic
            return c["score"] + bonus

        reranked = sorted(candidates, key=rerank_score, reverse=True)
        return reranked


def get_embedding_provider() -> EmbeddingProvider:
    return TfidfEmbeddingProvider()
