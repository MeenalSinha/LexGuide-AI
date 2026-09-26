import time
import logging
from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from app.core.config import settings
from app.core.rate_limit import rate_limit_middleware
from app.database import Base, engine
from app.api import documents, qa, compare, actionplan, brief, health

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("lexguide")

Base.metadata.create_all(bind=engine)

app = FastAPI(
    title=settings.APP_NAME,
    description="Evidence-first legal document intelligence & action assistant. "
                 "Does not provide legal representation or replace a qualified legal professional.",
    version="0.1.0",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"] if "*" in settings.CORS_ORIGINS else settings.CORS_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


app.middleware("http")(rate_limit_middleware)


@app.middleware("http")
async def security_headers_middleware(request: Request, call_next):
    """Baseline secure headers (spec §17 'Secure headers'). Conservative
    defaults appropriate for a JSON API + separately-hosted static frontend."""
    response = await call_next(request)
    response.headers["X-Content-Type-Options"] = "nosniff"
    response.headers["X-Frame-Options"] = "DENY"
    response.headers["Referrer-Policy"] = "no-referrer"
    response.headers["X-XSS-Protection"] = "0"  # deprecated header; explicit 0 avoids legacy browser quirks, CSP is the real defense
    response.headers["Permissions-Policy"] = "geolocation=(), microphone=(), camera=()"
    return response


@app.middleware("http")
async def error_sanitizing_and_logging(request: Request, call_next):
    """Structured logging (request_id/operation/latency) without ever logging
    document contents, and sanitized error responses (no stack traces)."""
    start = time.time()
    request_id = request.headers.get("x-request-id", str(time.time_ns()))
    try:
        response = await call_next(request)
        latency = (time.time() - start) * 1000
        logger.info(f"request_id={request_id} path={request.url.path} method={request.method} "
                    f"status={response.status_code} latency_ms={latency:.1f}")
        return response
    except Exception:
        latency = (time.time() - start) * 1000
        logger.exception(f"request_id={request_id} path={request.url.path} latency_ms={latency:.1f} error")
        return JSONResponse(
            status_code=500,
            content={"detail": "Something went wrong processing your request. Please try again."},
        )


app.include_router(documents.router)
app.include_router(qa.router)
app.include_router(compare.router)
app.include_router(actionplan.router)
app.include_router(brief.router)
app.include_router(health.router)


@app.get("/")
def root():
    return {
        "app": settings.APP_NAME,
        "tagline": "Understand the document. See the risks. Know what to ask next.",
        "disclaimer": "LexGuide AI provides legal information and document assistance. "
                       "It does not provide legal representation or replace a qualified legal professional.",
        "docs": "/docs",
    }
