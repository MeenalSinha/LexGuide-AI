# LexGuide AI — Architecture

## Overview

LexGuide AI is an evidence-first legal document intelligence assistant. Every
important answer is traceable to a specific document, page, and clause. The
system never claims to be a lawyer and never states a legal conclusion with
false confidence.

## Request flow (RAG pipeline)

```mermaid
flowchart TD
    A[Upload PDF/DOCX/TXT/MD] --> B[Parse: PyMuPDF / python-docx]
    B --> C[Page + heading structure detection]
    C --> D[Chunking with page/section metadata]
    D --> E[(DocumentChunk table)]
    E --> F[Clause segmentation]
    F --> G[Clause classification + attention scoring]
    G --> H[(Clause / Obligation / Deadline tables)]
    I[User question] --> J[Prompt-injection scan]
    J --> K[Hybrid retrieval: TF-IDF cosine + keyword overlap]
    K --> L{Score above grounding threshold?}
    L -- No --> M["I couldn't find this in the uploaded documents"]
    L -- Yes --> N[LLMProvider.answer_question with evidence only]
    N --> O[Response + citations + confidence]
```

## Component map

```
frontend/            Static HTML/CSS/JS SPA — Dashboard, Documents, Workspace,
                      Compare, Ask, Action Plan, Consultation Brief, Privacy.
                      No build step; talks to the backend over REST + CORS.

backend/app/
  main.py             FastAPI app, middleware (logging, error sanitizing), routers
  core/config.py       Central settings (env-driven)
  core/rate_limit.py    In-memory sliding-window rate limiter (spec §17)
  database.py           SQLAlchemy engine/session
  models.py              ORM models: Document, DocumentChunk, Clause,
                          Obligation, Deadline, QuestionLog, Comparison,
                          ActionPlan, ConsultationBrief, AuditLog
  providers/
    llm_provider.py       LLMProvider interface — DemoLLMProvider (offline,
                           deterministic) + AnthropicLLMProvider (real API,
                           with automatic fallback to Demo on any error)
    embedding_provider.py EmbeddingProvider interface — TfidfEmbeddingProvider
                           (hybrid semantic + keyword retrieval)
    ocr_provider.py        OCRProvider interface — NullOCRProvider flags
                            scanned pages for a future real OCR backend
  services/
    document_service.py    Parsing, page/section detection, chunking
    analysis_service.py    Document understanding, clause classification,
                            risk/attention scoring, obligation & deadline
                            extraction, document health check
    rag_service.py         Grounded Q&A + cross-document reasoning
    comparison_service.py  Clause-aligned diffing between two documents
    action_plan_service.py Action plan generation (DO_NOW/VERIFY/ASK_*)
    brief_service.py       Legal consultation brief generation
    export_service.py      Brief export: TXT / DOCX / PDF (python-docx, PyMuPDF)
    glossary_service.py    Module 8 — Legal Term Explainer (curated glossary,
                            grounded in each document's actual usage context)
    guardrails.py          Prompt-injection detection + instruction layering
  api/
    documents.py, qa.py, compare.py, actionplan.py, brief.py, health.py
```

## Why these providers are interfaces, not hard-coded calls

`LLMProvider`, `EmbeddingProvider`, and `OCRProvider` are abstract base
classes. Every service calls the *interface*, never a specific SDK. This
means:

- The whole product runs and is fully demonstrable with **zero external API
  calls** (`LLM_PROVIDER=demo`).
- Switching to a real model is a one-line env change
  (`LLM_PROVIDER=anthropic` + `ANTHROPIC_API_KEY=...`), with automatic
  fallback to the demo provider if the API call fails for any reason — the
  product never breaks mid-demo.
- Swapping in OpenAI/Gemini, a real embedding model, or a Tesseract/cloud OCR
  backend only requires a new class implementing the same interface — no
  caller changes anywhere in `services/` or `api/`.

## Production upgrade path (SQLite → Postgres + pgvector)

The prototype uses SQLite so it runs with zero setup. All models are written
in portable SQLAlchemy. To move to production:

1. Set `DATABASE_URL=postgresql+psycopg://user:pass@host/db` (see
   `docker-compose.yml` for a `pgvector/pgvector` service definition, commented
   out by default).
2. Replace `TfidfEmbeddingProvider` with a provider that calls a real
   embedding model and stores/queries vectors in a `pgvector` column instead
   of doing in-memory TF-IDF. The `EmbeddingProvider.retrieve()` interface
   stays identical, so `rag_service.py` requires no changes.
3. Add Celery + Redis for async document processing (chunking/embedding of
   very large PDFs) instead of the current synchronous upload-time pipeline.
   The `Document.status` field (`uploading|parsing|analyzing|indexing|ready`)
   already models this state machine.
4. Replace `NullOCRProvider` with a Tesseract or cloud OCR-backed
   implementation of `OCRProvider.extract_text()`.

## Hallucination defense

1. **Retrieval threshold** — `GROUNDING_MIN_SCORE` in `core/config.py`; below
   this, the system returns "I couldn't find this information in the
   uploaded documents" instead of guessing.
2. **Evidence-only generation** — `LLMProvider.answer_question()` is only
   ever given retrieved chunks, never asked to answer from general
   knowledge.
3. **Citation enforcement** — every grounded answer carries
   `document_name`, `page`, `section`, and an `excerpt`, sourced directly
   from a real `DocumentChunk` row.
4. **"Not found in document"** — `analysis_service.build_document_understanding()`
   explicitly returns this string for any field it cannot match, rather than
   guessing a plausible-sounding value.
5. **Document Health Check** — a separate structural-quality pass
   (`run_document_health_check`) flags broken cross-references, unfilled
   placeholders, duplicate headings, and missing dates — labeled as
   structural observations, not legal conclusions.

## Security

- File-type allowlist (`.pdf`, `.docx`, `.txt`, `.md`) and size limit,
  enforced server-side (`api/documents.py`).
- Uploaded files are stored under UUID-based filenames, never the original
  filename, to avoid path traversal / collision issues.
- **Prompt-injection defense**: `services/guardrails.py` scans every
  uploaded document and every user question for common injection patterns
  ("ignore previous instructions", "reveal your system prompt", etc.).
  Flagged content is never treated as an instruction — it is labeled and
  passed to the LLM strictly as `<document_data>` — and the UI surfaces a
  visible warning (see `test_prompt_injection_in_document_is_flagged_not_executed`
  in `tests/test_security.py`).
- Errors are sanitized centrally in `main.py` middleware — no stack traces
  are ever returned to the client; only a generic message plus a server-side
  structured log line.
- Structured logs never include document contents (`main.py` logs
  `request_id`, `path`, `status`, `latency_ms` only).
- CORS is explicitly configured (`CORS_ORIGINS` in `.env`).
- Rate limiting: an in-memory sliding-window limiter
  (`core/rate_limit.py`) throttles requests per client IP
  (`RATE_LIMIT_PER_MINUTE` in `.env`, default 120/min), exempting
  `/health` and the docs endpoints. Single-process only by design —
  a multi-replica deployment should swap this for a Redis-backed limiter
  (the interface would stay the same for callers).

## Instruction layering (prompt-injection architecture)

```
SYSTEM INSTRUCTIONS   (hard-coded in LLMProvider prompt templates)
        ↓
APPLICATION INSTRUCTIONS  (the specific task: "explain this clause", "answer from this evidence only")
        ↓
USER QUERY             (the person's question — treated as intent, not code)
        ↓
DOCUMENT DATA           (always wrapped in <document_data> tags; scanned for
                         injection attempts; NEVER concatenated as if it were
                         an instruction)
```

## Known limitations (see also README.md § Limitations)

- Clause/obligation/deadline extraction uses regex + heading heuristics, not
  a fine-tuned legal NLP model — it is tuned against the four demo documents
  and common contract patterns, but will miss unusual formatting.
- Retrieval is TF-IDF + keyword hybrid, not a trained embedding model — good
  enough for demo-scale documents, not a production semantic search
  replacement.
- Only English documents are supported.
- Jurisdiction selection in the UI is currently informational only; the
  Authoritative Legal Knowledge Layer (India Code / government sources) is
  not wired to a live retrieval source in this prototype — see README §
  Future Roadmap.
