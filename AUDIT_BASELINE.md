# AUDIT_BASELINE.md

**Scope:** state of the LexGuide AI repository at the start of this audit
pass (before Phase 3 repairs below were applied). Written from direct
inspection of the code, not from the existing README's claims.

## 1. Current architecture

- **Backend:** FastAPI (Python), SQLAlchemy ORM over SQLite, synchronous
  request handling (no Celery/background workers). Layered as
  `api/` → `services/` → `providers/` (interfaces for LLM / Embedding / OCR)
  → `models.py` (ORM).
- **Frontend:** Dependency-free HTML/CSS/JS single-page app, no build step,
  calling the backend over REST + CORS.
- **AI:** `LLMProvider` interface with a `DemoLLMProvider` (deterministic,
  offline, templated) as the default, and an `AnthropicLLMProvider` that
  falls back to demo behavior on any error.
- **Retrieval:** `EmbeddingProvider` interface, implemented as
  `TfidfEmbeddingProvider` (TF-IDF cosine similarity + keyword overlap
  hybrid) — no true dense embeddings, no vector database.
- **Storage:** SQLite via portable SQLAlchemy models; file uploads on local
  disk under UUID-based filenames.
- **Testing:** pytest, `TestClient`-based, 58 tests at the start of this
  pass.

## 2. Existing features (verified present and functional at baseline)

Document upload (PDF/DOCX/TXT/MD) and parsing, page/heading/paragraph
preservation, DOCX table extraction, document-type detection, executive
summary + document-understanding fields ("Not found in document" fallback),
per-clause plain-language explanation, clause categorization + attention
scoring with stated reasons, contract comparison (added/removed/modified,
category filters), grounded Q&A with citations and a "not found" path,
cross-document Q&A (backend + frontend, wired in a prior pass), obligation
and deadline extraction, document health check, action plan generation,
consultation brief generation + TXT/DOCX/PDF export, a 15-term Legal Term
Explainer glossary, prompt-injection detection, rate limiting, delete
one/delete all, accessibility-oriented markup (skip link, ARIA, focus
styles, reduced-motion), a guided demo, and 4 fictional demo documents.

## 3. Missing features (confirmed absent at baseline, addressed in Phase 3 below or left as documented scope)

Fixed in this pass (see FINAL_AUDIT_REPORT.md § Bugs Fixed / Missing
Features Added for detail):
- Jurisdiction selector existed in the UI but was **never sent to or stored
  by the backend** — purely cosmetic.
- A parse failure returned a bare `422` with **no database record created**
  — no "failed processing" state, no retry path, as the checklist requires.
- Obligation/deadline `source_heading`/`page` were **computed during
  extraction but silently dropped** before being persisted to the database
  — a real data-loss bug, not just a missing feature.
- No obligation checklist completion state (extraction existed; the
  "convert to checklist" behavior did not).
- No streaming Q&A response.
- No cross-document conflict/contradiction detection (cross-document Q&A
  existed; explicit conflict flagging did not).
- No explicit reranking stage in retrieval (single-pass TF-IDF+keyword only).
- No "Ambiguous language" clause detection/category.
- No security response headers (X-Frame-Options etc.).
- No content/MIME sniffing beyond file extension (a renamed executable with
  a `.txt` extension would previously have been accepted silently).
- No PDF table extraction (DOCX tables were extracted; PDF tables were not).

Left as documented, out-of-scope gaps (not attempted this pass — see
FINAL_IMPLEMENTATION_CHECKLIST.md for the full NO list and reasons):
real vector database (pgvector), Celery/Redis async processing, a real OCR
engine, a Next.js frontend, live external Authoritative Legal Source
retrieval (India Code etc.), multi-tenant authentication, malware-scanning
integration, and browser-driven (not static-analysis) accessibility testing.

## 4. Broken features

None found that were advertised as working and silently failed at
runtime — the main issues were **missing** persistence (obligation
source data) and **missing** wiring (jurisdiction), not broken logic in
what did run. See Bugs Found/Fixed in FINAL_AUDIT_REPORT.md.

## 5. Mocked functionality

- `DemoLLMProvider` is templated/deterministic by design, not a mock
  standing in for a broken real provider — it is documented as the
  intentional default so the whole product runs offline, and
  `AnthropicLLMProvider` is a real, working alternative when configured.
- `NullOCRProvider` intentionally does not perform real OCR; it flags
  scanned pages honestly rather than fabricating extracted text. This is
  documented as a limitation, not presented as working OCR.
- No functionality was found that displays a false "success" state for
  work that didn't happen (Rule 4) — this was specifically checked by
  writing tests against the actual API responses rather than trusting UI
  copy.

## 6. Technical debt

- In-memory rate limiter is single-process only (documented, acceptable for
  a single-instance prototype).
- TF-IDF retrieval will not scale semantic quality to large/varied document
  sets the way a trained embedding model would.
- No formal migrations system (SQLAlchemy `create_all` only) — fine for
  SQLite prototype scale, would need Alembic for a real Postgres rollout.

## 7. Security concerns (baseline)

- No MIME/content sniffing beyond extension allowlist (fixed this pass).
- No security response headers (fixed this pass).
- No malware scanning (still absent, documented, needs an external
  scanning service in production).
- No authentication (still absent, documented; ID-based isolation is real
  and tested, but there's no login/session/tenant model).

## 8. AI/RAG concerns (baseline)

- No reranking stage (fixed this pass — see `_rerank()` in
  `TfidfEmbeddingProvider`).
- No streaming (fixed this pass).
- No cross-document conflict detection (fixed this pass).
- Retrieval quality is TF-IDF-based, not a trained embedding model — this
  remains a genuine, documented limitation after this pass; it changes
  retrieval *ranking* quality, not the grounding/citation guarantees, which
  were independently verified via tests (every citation traces to real
  chunk text; ungrounded questions return "I couldn't find this").

## 9. Testing gaps (baseline)

At the start of this pass: 58 tests, covering unit/RAG/security/export/
accessibility(static)/frontend-wiring/E2E, but with no explicit coverage
for: reprocess/retry, jurisdiction persistence, obligation checklist state,
conflict detection, reranking behavior, streaming, content-sniffing, or
security headers — because those features didn't exist yet. All are now
covered (see `tests/test_audit_fixes.py`, 20 new tests; 78 total).

## 10. UX/accessibility gaps (baseline)

- Jurisdiction selector was present but functionally inert (confusing —
  looks configurable, wasn't).
- Documents that failed to parse simply vanished from the user's
  perspective (a 422 with nothing to look at, no retry affordance) — poor
  error-state UX, now fixed with a visible "error" row + Retry button.
- Obligations were listed but not actionable as a checklist despite the
  spec explicitly asking for that. Now fixed.
