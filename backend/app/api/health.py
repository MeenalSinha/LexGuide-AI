from fastapi import APIRouter
from app.core.config import settings

router = APIRouter(tags=["system"])


@router.get("/health")
def health():
    return {
        "status": "ok",
        "app": settings.APP_NAME,
        "env": settings.ENV,
        "llm_provider": settings.LLM_PROVIDER,
    }


@router.get("/metrics")
def metrics():
    """Internal/developer-only evaluation surface. In production this would
    be gated behind auth and would report parsing success rate, retrieval
    accuracy, citation accuracy, unsupported-claim rate, latency, and token
    usage pulled from the audit_log table. Kept minimal here to avoid
    exposing debugging internals to ordinary users."""
    from app.database import SessionLocal
    from app.models import AuditLog, Document, QuestionLog
    db = SessionLocal()
    try:
        total_docs = db.query(Document).count()
        total_questions = db.query(QuestionLog).count()
        grounded_questions = db.query(QuestionLog).filter(QuestionLog.grounded == True).count()  # noqa: E712
        grounding_rate = (grounded_questions / total_questions) if total_questions else None
        return {
            "documents_processed": total_docs,
            "questions_answered": total_questions,
            "grounding_rate": grounding_rate,
        }
    finally:
        db.close()
