import os
import time
from fastapi import APIRouter, UploadFile, File, Form, HTTPException, Depends
from sqlalchemy.orm import Session

from app.database import get_db
from app.core.config import settings
from app.models import Document, DocumentChunk, Clause, Obligation, Deadline, AuditLog
from app.services import document_service as docsvc
from app.services import analysis_service as analysis
from app.services.guardrails import scan_for_injection

router = APIRouter(prefix="/documents", tags=["documents"])


@router.post("/upload")
async def upload_document(file: UploadFile = File(...), jurisdiction: str = Form("Not specified"),
                           db: Session = Depends(get_db)):
    start = time.time()
    ext = os.path.splitext(file.filename)[1].lower()
    if ext not in settings.ALLOWED_EXTENSIONS:
        raise HTTPException(400, f"Unsupported file type '{ext}'. Allowed: {sorted(settings.ALLOWED_EXTENSIONS)}")

    file_bytes = await file.read()
    size_mb = len(file_bytes) / (1024 * 1024)
    if size_mb > settings.MAX_UPLOAD_MB:
        raise HTTPException(400, f"File exceeds {settings.MAX_UPLOAD_MB}MB limit.")

    content_ok, content_note = docsvc.sniff_content_matches_extension(file_bytes, ext)

    path = docsvc.save_upload(file_bytes, file.filename)
    jurisdiction = jurisdiction or "Not specified"

    try:
        parsed = docsvc.parse_document(path, ext)
    except Exception as e:
        # Failed processing state (spec: never silently fail) -- the document
        # is still recorded, in an 'error' state, with the file retained on
        # disk so it can be retried via POST /documents/{id}/reprocess.
        doc = Document(
            filename=file.filename, doc_type="Unknown", jurisdiction=jurisdiction,
            pages=0, word_count=0, status="error", file_path=path,
            error_message=f"Your document could not be parsed. ({type(e).__name__}: {e})",
            metadata_json={},
        )
        db.add(doc)
        db.commit()
        db.refresh(doc)
        return _document_summary(doc)

    flagged, injection_note = scan_for_injection(parsed["text"])
    doc_type = docsvc.detect_doc_type(file.filename, parsed["text"])

    doc = Document(
        filename=file.filename, doc_type=doc_type, jurisdiction=jurisdiction, pages=parsed["pages"],
        word_count=parsed["word_count"], status="analyzing", ocr_used=parsed["ocr_used"],
        raw_text=parsed["text"], file_path=path,
        metadata_json={
            "injection_flagged": flagged, "injection_note": injection_note,
            "content_mismatch": not content_ok, "content_mismatch_note": content_note,
        },
    )
    db.add(doc)
    db.commit()
    db.refresh(doc)

    _index_and_analyze(db, doc)

    db.add(AuditLog(operation="document.upload", document_id=doc.id, latency_ms=(time.time() - start) * 1000))
    db.commit()

    return _document_summary(doc)


@router.post("/{doc_id}/reprocess")
def reprocess_document(doc_id: str, db: Session = Depends(get_db)):
    """Retry the parse+analyze pipeline for a document stuck in 'error'
    status (e.g. after a transient failure), without re-uploading the file."""
    doc = db.get(Document, doc_id)
    if not doc:
        raise HTTPException(404, "Document not found.")
    if not doc.file_path or not os.path.exists(doc.file_path):
        raise HTTPException(400, "Original file is no longer available; please re-upload.")

    ext = os.path.splitext(doc.filename)[1].lower()
    try:
        parsed = docsvc.parse_document(doc.file_path, ext)
    except Exception as e:
        doc.status = "error"
        doc.error_message = f"Reprocessing failed. ({type(e).__name__}: {e})"
        db.commit()
        return _document_summary(doc)

    flagged, injection_note = scan_for_injection(parsed["text"])
    doc.doc_type = docsvc.detect_doc_type(doc.filename, parsed["text"])
    doc.pages = parsed["pages"]
    doc.word_count = parsed["word_count"]
    doc.ocr_used = parsed["ocr_used"]
    doc.raw_text = parsed["text"]
    doc.error_message = ""
    doc.status = "analyzing"
    doc.metadata_json = {**(doc.metadata_json or {}), "injection_flagged": flagged, "injection_note": injection_note}

    # Clear previously derived data before re-deriving it
    db.query(DocumentChunk).filter(DocumentChunk.document_id == doc.id).delete()
    db.query(Clause).filter(Clause.document_id == doc.id).delete()
    db.query(Obligation).filter(Obligation.document_id == doc.id).delete()
    db.query(Deadline).filter(Deadline.document_id == doc.id).delete()
    db.commit()
    db.refresh(doc)

    _index_and_analyze(db, doc)
    return _document_summary(doc)


def _index_and_analyze(db: Session, doc: Document):
    chunks = docsvc.chunk_document(doc.id, doc.raw_text)
    for c in chunks:
        db.add(DocumentChunk(document_id=doc.id, chunk_index=c["chunk_index"], page=c["page"],
                              section=c["section"], text=c["text"]))

    candidate_clauses = analysis.split_into_candidate_clauses(doc.raw_text)
    stored_clauses = []
    clause_by_heading = {}
    for cc in candidate_clauses:
        category = analysis.classify_clause_category(cc["text"], cc["heading"])
        assessment = analysis.assess_attention(cc["text"], category)
        clause = Clause(document_id=doc.id, heading=cc["heading"], category=category,
                         attention=assessment["attention"], reason=assessment["reason"],
                         text=cc["text"], page=cc["page"])
        db.add(clause)
        stored_clauses.append(clause)
        clause_by_heading[cc["heading"]] = clause
    db.flush()

    obligations = analysis.extract_obligations(candidate_clauses)
    for o in obligations:
        source_clause = clause_by_heading.get(o.get("source_heading", ""))
        db.add(Obligation(document_id=doc.id, who=o["who"], what=o["what"], when=o["when"],
                           condition=o["condition"], source_heading=o.get("source_heading", ""),
                           page=o.get("page"),
                           source_clause_id=source_clause.id if source_clause else ""))

    deadlines = analysis.extract_deadlines(candidate_clauses)
    for d in deadlines:
        source_clause = clause_by_heading.get(d.get("source_heading", ""))
        db.add(Deadline(document_id=doc.id, label=d["label"], date_text=d["date_text"],
                         source_heading=d.get("source_heading", ""), page=d.get("page"),
                         source_clause_id=source_clause.id if source_clause else ""))

    doc.status = "ready"
    db.commit()


def _document_summary(doc: Document):
    return {
        "id": doc.id, "filename": doc.filename, "doc_type": doc.doc_type,
        "jurisdiction": doc.jurisdiction,
        "pages": doc.pages, "word_count": doc.word_count, "status": doc.status,
        "ocr_used": doc.ocr_used, "created_at": doc.created_at.isoformat(),
        "error_message": doc.error_message or "",
        "injection_flagged": (doc.metadata_json or {}).get("injection_flagged", False),
        "injection_note": (doc.metadata_json or {}).get("injection_note", ""),
        "content_mismatch": (doc.metadata_json or {}).get("content_mismatch", False),
        "content_mismatch_note": (doc.metadata_json or {}).get("content_mismatch_note", ""),
    }


@router.get("")
def list_documents(db: Session = Depends(get_db)):
    docs = db.query(Document).order_by(Document.created_at.desc()).all()
    return [_document_summary(d) for d in docs]


@router.get("/{doc_id}")
def get_document(doc_id: str, db: Session = Depends(get_db)):
    doc = db.get(Document, doc_id)
    if not doc:
        raise HTTPException(404, "Document not found.")
    return {**_document_summary(doc), "raw_text": doc.raw_text}


@router.delete("/{doc_id}")
def delete_document(doc_id: str, db: Session = Depends(get_db)):
    doc = db.get(Document, doc_id)
    if not doc:
        raise HTTPException(404, "Document not found.")
    db.delete(doc)
    db.commit()
    return {"deleted": True, "id": doc_id}


@router.delete("")
def delete_all_documents(db: Session = Depends(get_db)):
    count = db.query(Document).count()
    db.query(Document).delete()
    db.commit()
    return {"deleted": True, "count": count}


@router.get("/{doc_id}/insights")
def get_insights(doc_id: str, db: Session = Depends(get_db)):
    doc = db.get(Document, doc_id)
    if not doc:
        raise HTTPException(404, "Document not found.")
    if doc.status == "error":
        raise HTTPException(400, f"This document could not be analyzed: {doc.error_message or 'processing failed'}. "
                                  f"Use POST /documents/{doc_id}/reprocess to retry.")

    clauses = db.query(Clause).filter(Clause.document_id == doc_id).all()
    obligations = db.query(Obligation).filter(Obligation.document_id == doc_id).all()
    deadlines = db.query(Deadline).filter(Deadline.document_id == doc_id).all()

    clause_dicts = [{"id": c.id, "heading": c.heading, "category": c.category, "attention": c.attention,
                      "reason": c.reason, "text": c.text, "page": c.page} for c in clauses]

    summary = analysis.generate_executive_summary(doc.doc_type, doc.raw_text)
    understanding = analysis.build_document_understanding(doc.doc_type, clause_dicts)
    health_issues = analysis.run_document_health_check(doc.raw_text, clause_dicts)

    attention_counts = {"HIGH": 0, "MEDIUM": 0, "LOW": 0}
    for c in clause_dicts:
        attention_counts[c["attention"]] = attention_counts.get(c["attention"], 0) + 1

    return {
        "document": _document_summary(doc),
        "executive_summary": summary,
        "understanding": understanding,
        "clauses": clause_dicts,
        "attention_counts": attention_counts,
        "obligations": [{"id": o.id, "who": o.who, "what": o.what, "when": o.when, "page": o.page,
                          "source_heading": o.source_heading, "source_clause_id": o.source_clause_id,
                          "completed": o.completed} for o in obligations],
        "deadlines": [{"id": d.id, "label": d.label, "date_text": d.date_text, "page": d.page,
                        "source_heading": d.source_heading, "source_clause_id": d.source_clause_id} for d in deadlines],
        "health_check": health_issues,
        "analytics": {
            "pages": doc.pages, "clauses_detected": len(clause_dicts),
            "obligations_detected": len(obligations), "deadlines_detected": len(deadlines),
            "attention_areas": attention_counts["HIGH"] + attention_counts["MEDIUM"],
        },
    }


@router.patch("/{doc_id}/obligations/{obligation_id}")
def update_obligation(doc_id: str, obligation_id: str, completed: bool, db: Session = Depends(get_db)):
    """Obligation checklist completion state (spec: 'Allow users to convert
    obligations into a checklist')."""
    obligation = db.get(Obligation, obligation_id)
    if not obligation or obligation.document_id != doc_id:
        raise HTTPException(404, "Obligation not found.")
    obligation.completed = completed
    db.commit()
    return {"id": obligation.id, "completed": obligation.completed}


@router.post("/{doc_id}/explain-clause/{clause_id}")
def explain_clause(doc_id: str, clause_id: str, db: Session = Depends(get_db)):
    clause = db.get(Clause, clause_id)
    if not clause or clause.document_id != doc_id:
        raise HTTPException(404, "Clause not found.")
    from app.providers.llm_provider import get_llm_provider
    llm = get_llm_provider()
    explanation = llm.plain_language(clause.text, clause.category)
    return {
        "clause": {"id": clause.id, "heading": clause.heading, "category": clause.category,
                    "attention": clause.attention, "reason": clause.reason, "text": clause.text, "page": clause.page},
        "plain_language": explanation,
        "source_type": "DOCUMENT SOURCE",
    }


@router.get("/glossary/terms")
def list_glossary_terms():
    """MODULE 8 — Legal Term Explainer: list of supported terms."""
    from app.services.glossary_service import list_terms
    return {"terms": list_terms()}


@router.get("/{doc_id}/glossary/{term}")
def explain_glossary_term(doc_id: str, term: str, db: Session = Depends(get_db)):
    """MODULE 8 — Legal Term Explainer: definition + this document's actual
    usage context for a given term."""
    doc = db.get(Document, doc_id)
    if not doc:
        raise HTTPException(404, "Document not found.")
    from app.services.glossary_service import explain_term
    result = explain_term(term, doc.raw_text)
    if not result:
        raise HTTPException(404, f"'{term}' is not in the glossary. See /glossary/terms for supported terms.")
    return result
