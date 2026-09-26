from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import Response
from sqlalchemy.orm import Session
from app.database import get_db
from app.schemas import BriefRequest
from app.models import Document, Clause, Obligation, Deadline, ConsultationBrief
from app.services import analysis_service as analysis
from app.services.brief_service import generate_brief
from app.services.export_service import brief_to_text, brief_to_docx_bytes, brief_to_pdf_bytes

router = APIRouter(tags=["brief"])


@router.post("/consultation-brief")
def create_brief(req: BriefRequest, db: Session = Depends(get_db)):
    documents = []
    for doc_id in req.document_ids:
        doc = db.get(Document, doc_id)
        if not doc:
            raise HTTPException(404, f"Document {doc_id} not found.")
        clauses = db.query(Clause).filter(Clause.document_id == doc_id).all()
        deadlines = db.query(Deadline).filter(Deadline.document_id == doc_id).all()
        clause_dicts = [{"heading": c.heading, "category": c.category, "attention": c.attention, "page": c.page, "text": c.text} for c in clauses]
        deadline_dicts = [{"label": d.label, "date_text": d.date_text} for d in deadlines]
        understanding = analysis.build_document_understanding(doc.doc_type, clause_dicts)
        documents.append({
            "filename": doc.filename, "doc_type": doc.doc_type, "clauses": clause_dicts,
            "deadlines": deadline_dicts, "understanding": understanding,
        })

    brief = generate_brief(documents, req.concerns or "")
    record = ConsultationBrief(document_ids=req.document_ids, brief_json=brief)
    db.add(record)
    db.commit()
    db.refresh(record)
    brief["id"] = record.id
    return brief


@router.get("/consultation-brief/{brief_id}")
def get_brief(brief_id: str, db: Session = Depends(get_db)):
    record = db.get(ConsultationBrief, brief_id)
    if not record:
        raise HTTPException(404, "Brief not found.")
    return record.brief_json


@router.get("/consultation-brief/{brief_id}/export")
def export_brief(brief_id: str, format: str = "txt", db: Session = Depends(get_db)):
    record = db.get(ConsultationBrief, brief_id)
    if not record:
        raise HTTPException(404, "Brief not found.")
    brief = record.brief_json
    fmt = format.lower()

    if fmt == "txt":
        content = brief_to_text(brief).encode("utf-8")
        media_type = "text/plain"
        filename = f"consultation_brief_{brief_id[:8]}.txt"
    elif fmt == "docx":
        content = brief_to_docx_bytes(brief)
        media_type = "application/vnd.openxmlformats-officedocument.wordprocessingml.document"
        filename = f"consultation_brief_{brief_id[:8]}.docx"
    elif fmt == "pdf":
        content = brief_to_pdf_bytes(brief)
        media_type = "application/pdf"
        filename = f"consultation_brief_{brief_id[:8]}.pdf"
    else:
        raise HTTPException(400, "format must be one of: txt, docx, pdf")

    return Response(
        content=content, media_type=media_type,
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )
