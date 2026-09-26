"""
MODULE 6 — Ask Your Document / MODULE 7 — Multi-document Q&A
Implements: retrieve -> sufficiency check -> generate -> citation attach.
Hallucination defense: if retrieval score is below GROUNDING_MIN_SCORE,
respond with "I couldn't find this information" rather than guessing.
"""
from typing import List, Dict
from sqlalchemy.orm import Session
from app.models import DocumentChunk, Document, QuestionLog
from app.providers.embedding_provider import get_embedding_provider
from app.providers.llm_provider import get_llm_provider
from app.services.guardrails import scan_for_injection
from app.services.conflict_service import detect_cross_document_conflicts
from app.core.config import settings


def answer_question(db: Session, question: str, document_ids: List[str]) -> Dict:
    flagged, note = scan_for_injection(question)

    chunks_q = db.query(DocumentChunk)
    if document_ids:
        chunks_q = chunks_q.filter(DocumentChunk.document_id.in_(document_ids))
    all_chunks = chunks_q.all()

    chunk_dicts = []
    doc_names = {d.id: d.filename for d in db.query(Document).all()}
    for c in all_chunks:
        chunk_dicts.append({
            "id": c.id, "document_id": c.document_id,
            "document_name": doc_names.get(c.document_id, "Unknown document"),
            "page": c.page, "section": c.section, "text": c.text,
        })

    embedder = get_embedding_provider()
    retrieved = embedder.retrieve(question, chunk_dicts, settings.RETRIEVAL_TOP_K)
    sufficient = bool(retrieved) and retrieved[0]["score"] >= settings.GROUNDING_MIN_SCORE
    evidence_for_llm = retrieved if sufficient else []

    llm = get_llm_provider()
    result = llm.answer_question(question, evidence_for_llm)

    evidence = [{
        "document_name": e["document_name"], "page": e["page"],
        "section": e["section"] or "Unspecified section",
        "excerpt": e["text"][:300], "score": e["score"],
    } for e in (retrieved[:3] if sufficient else [])]

    response = {
        "answer": result["answer"],
        "grounded": result["grounded"] and sufficient,
        "confidence": "high" if sufficient and retrieved[0]["score"] > 0.35 else ("medium" if sufficient else "low"),
        "evidence": evidence,
        "source_type": "DOCUMENT SOURCE" if sufficient else "NONE",
        "injection_notice": note if flagged else None,
    }

    log = QuestionLog(
        document_ids=document_ids, question=question, answer=result["answer"],
        grounded=response["grounded"], evidence=evidence,
    )
    db.add(log)
    db.commit()

    return response


def cross_document_relationship(db: Session, doc_a_id: str, doc_b_id: str, question: str) -> Dict:
    """MODULE 7 — cross-document reasoning: retrieve top evidence independently
    from each document, then let the LLM compare only those grounded excerpts.
    Also runs conflict/contradiction detection (spec §F) between the two
    documents' shared clause categories."""
    embedder = get_embedding_provider()
    docs = {d.id: d for d in db.query(Document).all()}
    doc_names = {i: d.filename for i, d in docs.items()}

    def top_for(doc_id):
        chunks = db.query(DocumentChunk).filter(DocumentChunk.document_id == doc_id).all()
        dicts = [{"id": c.id, "document_id": c.document_id, "document_name": doc_names.get(doc_id, ""),
                  "page": c.page, "section": c.section, "text": c.text} for c in chunks]
        return embedder.retrieve(question, dicts, 3)

    ev_a = top_for(doc_a_id)
    ev_b = top_for(doc_b_id)
    llm = get_llm_provider()
    combined_evidence = ev_a + ev_b
    result = llm.answer_question(question, combined_evidence)

    conflicts = []
    if doc_a_id in docs and doc_b_id in docs:
        conflicts = detect_cross_document_conflicts(
            doc_names[doc_a_id], docs[doc_a_id].raw_text,
            doc_names[doc_b_id], docs[doc_b_id].raw_text,
        )

    return {
        "document_a": doc_names.get(doc_a_id, ""),
        "document_b": doc_names.get(doc_b_id, ""),
        "answer": result["answer"] if combined_evidence else "I couldn't find this information in the uploaded documents.",
        "evidence_a": [{"page": e["page"], "section": e["section"], "excerpt": e["text"][:250]} for e in ev_a],
        "evidence_b": [{"page": e["page"], "section": e["section"], "excerpt": e["text"][:250]} for e in ev_b],
        "potential_conflicts": conflicts,
    }
