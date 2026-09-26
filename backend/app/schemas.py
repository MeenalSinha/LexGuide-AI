from pydantic import BaseModel
from typing import List, Optional, Dict, Any


class QuestionRequest(BaseModel):
    question: str
    document_ids: List[str] = []


class CompareRequest(BaseModel):
    document_a_id: str
    document_b_id: str


class CrossDocQuestionRequest(BaseModel):
    document_a_id: str
    document_b_id: str
    question: str


class ActionPlanRequest(BaseModel):
    document_id: str


class BriefRequest(BaseModel):
    document_ids: List[str]
    concerns: Optional[str] = ""


class ClauseExplainRequest(BaseModel):
    clause_id: str
