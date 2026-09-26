"""
Closes acceptance-checklist items 'PDF parsing works' / 'DOCX parsing works'
/ 'OCR fallback works' with REAL generated files, not just .txt fixtures.
"""
import os
from tests.fixtures_gen import make_pdf, make_scanned_pdf, make_docx, tmp_file
from app.services import document_service as docsvc


def test_parse_real_pdf_extracts_text_and_pages():
    path = tmp_file(".pdf")
    make_pdf(path)
    try:
        parsed = docsvc.parse_document(path, ".pdf")
        assert parsed["pages"] == 2
        assert "TERMINATION" in parsed["text"]
        assert "COMPENSATION" in parsed["text"]
        assert parsed["ocr_used"] is False
        assert parsed["word_count"] > 0
    finally:
        os.remove(path)


def test_parse_scanned_pdf_flags_ocr_fallback():
    path = tmp_file(".pdf")
    make_scanned_pdf(path)
    try:
        parsed = docsvc.parse_document(path, ".pdf")
        assert parsed["ocr_used"] is True
        assert "OCR" in parsed["text"]
    finally:
        os.remove(path)


def test_parse_real_docx_extracts_text_and_tables():
    path = tmp_file(".docx")
    make_docx(path)
    try:
        parsed = docsvc.parse_document(path, ".docx")
        assert "EMPLOYMENT AGREEMENT" in parsed["text"]
        assert "NovaTech Solutions" in parsed["text"]  # from the table
        assert parsed["pages"] == 1
    finally:
        os.remove(path)


def test_upload_real_pdf_end_to_end(client):
    path = tmp_file(".pdf")
    make_pdf(path)
    try:
        with open(path, "rb") as f:
            r = client.post("/documents/upload", files={"file": ("real.pdf", f, "application/pdf")})
        assert r.status_code == 200
        body = r.json()
        assert body["pages"] == 2
        ins = client.get(f"/documents/{body['id']}/insights")
        assert ins.status_code == 200
        assert ins.json()["analytics"]["clauses_detected"] > 0
    finally:
        os.remove(path)


def test_upload_real_docx_end_to_end(client):
    path = tmp_file(".docx")
    make_docx(path)
    try:
        with open(path, "rb") as f:
            r = client.post("/documents/upload", files={"file": ("real.docx", f,
                "application/vnd.openxmlformats-officedocument.wordprocessingml.document")})
        assert r.status_code == 200
        body = r.json()
        assert body["status"] == "ready"
    finally:
        os.remove(path)


def test_upload_scanned_pdf_surfaces_ocr_flag_via_api(client):
    path = tmp_file(".pdf")
    make_scanned_pdf(path)
    try:
        with open(path, "rb") as f:
            r = client.post("/documents/upload", files={"file": ("scanned.pdf", f, "application/pdf")})
        assert r.status_code == 200
        assert r.json()["ocr_used"] is True
    finally:
        os.remove(path)
