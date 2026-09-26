from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from app.database import get_db
from app.schemas import ActionPlanRequest
from app.models import Document, Clause, Obligation, Deadline, ActionPlan
from app.services import analysis_service as analysis
from app.services.action_plan_service import generate_action_plan

router = APIRouter(tags=["action-plan"])


@router.post("/action-plan")
def create_action_plan(req: ActionPlanRequest, db: Session = Depends(get_db)):
    doc = db.get(Document, req.document_id)
    if not doc:
        raise HTTPException(404, "Document not found.")

    clauses = db.query(Clause).filter(Clause.document_id == doc.id).all()
    obligations = db.query(Obligation).filter(Obligation.document_id == doc.id).all()
    deadlines = db.query(Deadline).filter(Deadline.document_id == doc.id).all()

    clause_dicts = [{"heading": c.heading, "category": c.category, "attention": c.attention, "page": c.page, "text": c.text} for c in clauses]
    obligation_dicts = [{"who": o.who, "what": o.what, "when": o.when} for o in obligations]
    deadline_dicts = [{"label": d.label, "date_text": d.date_text, "source_heading": d.label, "page": None} for d in deadlines]
    understanding = analysis.build_document_understanding(doc.doc_type, clause_dicts)

    items = generate_action_plan(doc.doc_type, clause_dicts, obligation_dicts, deadline_dicts, understanding)

    record = ActionPlan(document_id=doc.id, items_json=items)
    db.add(record)
    db.commit()
    db.refresh(record)

    grouped = {"DO_NOW": [], "VERIFY": [], "ASK_OTHER_PARTY": [], "ASK_LAWYER": []}
    for item in items:
        grouped.setdefault(item["category"], []).append(item)

    return {"id": record.id, "document": {"id": doc.id, "filename": doc.filename}, "items": items, "grouped": grouped}
