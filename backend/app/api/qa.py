from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import StreamingResponse
from sqlalchemy.orm import Session
import asyncio
import json
from app.database import get_db
from app.schemas import QuestionRequest, CrossDocQuestionRequest
from app.services import rag_service

router = APIRouter(tags=["qa"])


@router.post("/questions")
def ask_question(req: QuestionRequest, db: Session = Depends(get_db)):
    if not req.question.strip():
        raise HTTPException(400, "Question cannot be empty.")
    return rag_service.answer_question(db, req.question, req.document_ids)


@router.post("/questions/stream")
async def ask_question_stream(req: QuestionRequest, db: Session = Depends(get_db)):
    """Streaming variant of /questions (spec §E 'Streaming response').
    Retrieval + grounding validation happen fully server-side first (streaming
    must never mean streaming an ungrounded, half-checked answer) -- what's
    streamed to the client is the resulting grounded answer's text, sent as
    real chunked HTTP output, plus a final event carrying the structured
    evidence/citations once the text is complete."""
    if not req.question.strip():
        raise HTTPException(400, "Question cannot be empty.")

    result = rag_service.answer_question(db, req.question, req.document_ids)

    async def event_stream():
        words = result["answer"].split(" ")
        for i, word in enumerate(words):
            chunk = word + (" " if i < len(words) - 1 else "")
            yield f"data: {json.dumps({'type': 'token', 'text': chunk})}\n\n"
            await asyncio.sleep(0.01)
        final = {k: v for k, v in result.items() if k != "answer"}
        yield f"data: {json.dumps({'type': 'done', **final})}\n\n"

    return StreamingResponse(event_stream(), media_type="text/event-stream")


@router.post("/questions/cross-document")
def ask_cross_document(req: CrossDocQuestionRequest, db: Session = Depends(get_db)):
    return rag_service.cross_document_relationship(db, req.document_a_id, req.document_b_id, req.question)
