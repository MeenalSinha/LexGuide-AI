from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from app.database import get_db
from app.schemas import CompareRequest
from app.models import Document, Comparison
from app.services.comparison_service import compare_documents

router = APIRouter(tags=["compare"])


@router.post("/compare")
def create_comparison(req: CompareRequest, db: Session = Depends(get_db)):
    doc_a = db.get(Document, req.document_a_id)
    doc_b = db.get(Document, req.document_b_id)
    if not doc_a or not doc_b:
        raise HTTPException(404, "One or both documents not found.")

    result = compare_documents(doc_a.raw_text, doc_b.raw_text)
    result["document_a"] = {"id": doc_a.id, "filename": doc_a.filename}
    result["document_b"] = {"id": doc_b.id, "filename": doc_b.filename}

    record = Comparison(document_a_id=doc_a.id, document_b_id=doc_b.id, result_json=result)
    db.add(record)
    db.commit()
    db.refresh(record)
    result["comparison_id"] = record.id
    return result


@router.get("/compare/{comparison_id}")
def get_comparison(comparison_id: str, db: Session = Depends(get_db)):
    record = db.get(Comparison, comparison_id)
    if not record:
        raise HTTPException(404, "Comparison not found.")
    return record.result_json
