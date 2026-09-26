import uuid
import datetime as dt
from sqlalchemy import Column, String, Integer, Text, DateTime, ForeignKey, Float, JSON, Boolean
from sqlalchemy.orm import relationship
from app.database import Base

def uid():
    return str(uuid.uuid4())

class Document(Base):
    __tablename__ = "documents"
    id = Column(String, primary_key=True, default=uid)
    filename = Column(String, nullable=False)
    doc_type = Column(String, default="Unknown")          # Employment Agreement, NDA, etc
    jurisdiction = Column(String, default="Not specified")
    pages = Column(Integer, default=0)
    word_count = Column(Integer, default=0)
    status = Column(String, default="uploaded")            # uploading|parsing|analyzing|indexing|ready|error
    ocr_used = Column(Boolean, default=False)
    raw_text = Column(Text, default="")
    file_path = Column(String, default="")                 # stored path, enables reprocess after failure
    error_message = Column(Text, default="")
    metadata_json = Column(JSON, default=dict)
    created_at = Column(DateTime, default=dt.datetime.utcnow)

    chunks = relationship("DocumentChunk", back_populates="document", cascade="all, delete-orphan")
    clauses = relationship("Clause", back_populates="document", cascade="all, delete-orphan")
    obligations = relationship("Obligation", back_populates="document", cascade="all, delete-orphan")
    deadlines = relationship("Deadline", back_populates="document", cascade="all, delete-orphan")

class DocumentChunk(Base):
    __tablename__ = "document_chunks"
    id = Column(String, primary_key=True, default=uid)
    document_id = Column(String, ForeignKey("documents.id"))
    chunk_index = Column(Integer)
    page = Column(Integer, default=None, nullable=True)
    section = Column(String, default="")
    text = Column(Text)
    document = relationship("Document", back_populates="chunks")

class Clause(Base):
    __tablename__ = "clauses"
    id = Column(String, primary_key=True, default=uid)
    document_id = Column(String, ForeignKey("documents.id"))
    heading = Column(String, default="")
    category = Column(String, default="Informational")     # Obligation, Financial, Termination, ...
    attention = Column(String, default="LOW")               # LOW|MEDIUM|HIGH
    reason = Column(Text, default="")
    text = Column(Text)
    page = Column(Integer, default=None, nullable=True)
    document = relationship("Document", back_populates="clauses")

class Obligation(Base):
    __tablename__ = "obligations"
    id = Column(String, primary_key=True, default=uid)
    document_id = Column(String, ForeignKey("documents.id"))
    who = Column(String, default="")
    what = Column(Text, default="")
    when = Column(String, default="")
    condition = Column(String, default="")
    source_clause_id = Column(String, default="")
    source_heading = Column(String, default="")
    page = Column(Integer, default=None, nullable=True)
    completed = Column(Boolean, default=False)              # obligation checklist completion state
    document = relationship("Document", back_populates="obligations")

class Deadline(Base):
    __tablename__ = "deadlines"
    id = Column(String, primary_key=True, default=uid)
    document_id = Column(String, ForeignKey("documents.id"))
    label = Column(String, default="")
    date_text = Column(String, default="")
    source_clause_id = Column(String, default="")
    source_heading = Column(String, default="")
    page = Column(Integer, default=None, nullable=True)
    document = relationship("Document", back_populates="deadlines")

class QuestionLog(Base):
    __tablename__ = "questions"
    id = Column(String, primary_key=True, default=uid)
    document_ids = Column(JSON, default=list)
    question = Column(Text)
    answer = Column(Text)
    grounded = Column(Boolean, default=False)
    evidence = Column(JSON, default=list)
    created_at = Column(DateTime, default=dt.datetime.utcnow)

class Comparison(Base):
    __tablename__ = "comparisons"
    id = Column(String, primary_key=True, default=uid)
    document_a_id = Column(String)
    document_b_id = Column(String)
    result_json = Column(JSON, default=dict)
    created_at = Column(DateTime, default=dt.datetime.utcnow)

class ActionPlan(Base):
    __tablename__ = "action_plans"
    id = Column(String, primary_key=True, default=uid)
    document_id = Column(String)
    items_json = Column(JSON, default=list)
    created_at = Column(DateTime, default=dt.datetime.utcnow)

class ConsultationBrief(Base):
    __tablename__ = "consultation_briefs"
    id = Column(String, primary_key=True, default=uid)
    document_ids = Column(JSON, default=list)
    brief_json = Column(JSON, default=dict)
    created_at = Column(DateTime, default=dt.datetime.utcnow)

class AuditLog(Base):
    __tablename__ = "audit_log"
    id = Column(String, primary_key=True, default=uid)
    request_id = Column(String, default=uid)
    operation = Column(String)
    document_id = Column(String, default="")
    latency_ms = Column(Float, default=0.0)
    error_type = Column(String, default="")
    created_at = Column(DateTime, default=dt.datetime.utcnow)
