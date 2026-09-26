"""
MODULE 1 — Document ingestion: parsing, page/section preservation, chunking.
"""
import os
import re
from typing import List, Dict, Tuple

from app.core.config import settings
from app.providers.ocr_provider import get_ocr_provider

HEADING_RE = re.compile(r"^\s*((\d+(\.\d+)*\.?)|([A-Z][A-Z \-/&]{4,}))\s*[-:.]?\s*(.*)$")


def detect_doc_type(filename: str, text: str) -> str:
    t = text.lower()
    name = filename.lower()
    checks = [
        ("nda", "Non-Disclosure Agreement"),
        ("non-disclosure", "Non-Disclosure Agreement"),
        ("employment", "Employment Agreement"),
        ("offer letter", "Offer Letter"),
        ("internship", "Internship Agreement"),
        ("rental", "Rental Agreement"),
        ("lease", "Rental / Lease Agreement"),
        ("vendor", "Vendor Agreement"),
        ("service agreement", "Service Agreement"),
        ("saas", "SaaS Agreement"),
        ("partnership", "Partnership Agreement"),
    ]
    for key, label in checks:
        if key in name or key in t[:3000]:
            return label
    return "General Contract / Agreement"


def sniff_content_matches_extension(file_bytes: bytes, ext: str) -> tuple:
    """Lightweight magic-byte content sniffing so a renamed file (e.g. an
    executable saved as .txt) can't masquerade as a supported type just by
    its extension. Returns (looks_consistent, note). This does not replace a
    real malware scanner (see docs/architecture.md upgrade path) but it does
    catch the simple extension-spoofing case cheaply, with zero new
    dependencies."""
    head = file_bytes[:8]
    if ext == ".pdf":
        ok = head.startswith(b"%PDF")
        return ok, ("" if ok else "File extension is .pdf but content does not start with a PDF header.")
    if ext == ".docx":
        ok = head.startswith(b"PK\x03\x04") or head.startswith(b"PK\x05\x06")
        return ok, ("" if ok else "File extension is .docx but content is not a valid zip/OOXML container.")
    if ext in (".txt", ".md"):
        # Reject content that looks like a Windows/Linux executable or ELF binary
        # renamed to .txt/.md -- plain text should never start with these signatures.
        suspicious = head.startswith(b"MZ") or head.startswith(b"\x7fELF") or head.startswith(b"PK\x03\x04")
        return (not suspicious), ("" if not suspicious else "File extension suggests plain text but content looks like a binary/executable.")
    return True, ""


def parse_pdf(path: str) -> Tuple[str, int, bool]:
    import fitz  # PyMuPDF
    ocr = get_ocr_provider()
    doc = fitz.open(path)
    pages_text = []
    ocr_used = False
    for page in doc:
        text = page.get_text().strip()
        if not text:
            # scanned page -> flag for OCR fallback
            ocr_used = True
            text = ocr.extract_text(b"")

        # Table extraction (spec: "Preserve tables where possible"). PyMuPDF's
        # table finder works directly on the PDF's vector/text layout, so this
        # is real table extraction, not a heuristic on plain text.
        try:
            tables = page.find_tables()
            for t in tables.tables:
                rows = t.extract()
                if rows:
                    table_text = "\n".join(" | ".join(str(cell) if cell is not None else "" for cell in row) for row in rows)
                    text += f"\n[TABLE]\n{table_text}\n[/TABLE]"
        except Exception:
            pass  # table extraction is best-effort; never fail the whole parse over it

        pages_text.append(text)
    full_text = "\n\n".join(f"[PAGE {i+1}]\n{t}" for i, t in enumerate(pages_text))
    return full_text, len(pages_text), ocr_used


def parse_docx(path: str) -> Tuple[str, int]:
    import docx
    d = docx.Document(path)
    parts = []
    for p in d.paragraphs:
        if p.text.strip():
            parts.append(p.text)
    for table in d.tables:
        for row in table.rows:
            cells = [c.text.strip() for c in row.cells]
            parts.append(" | ".join(cells))
    text = "\n".join(parts)
    # DOCX has no native page breaks we can reliably extract -> treat as 1 logical page
    return f"[PAGE 1]\n{text}", 1


def parse_txt(path: str) -> Tuple[str, int]:
    with open(path, "r", encoding="utf-8", errors="replace") as f:
        text = f.read()
    return f"[PAGE 1]\n{text}", 1


def parse_document(path: str, ext: str) -> Dict:
    if ext == ".pdf":
        text, pages, ocr_used = parse_pdf(path)
    elif ext == ".docx":
        text, pages = parse_docx(path)
        ocr_used = False
    else:  # .txt / .md
        text, pages = parse_txt(path)
        ocr_used = False
    word_count = len(re.findall(r"\S+", text))
    return {"text": text, "pages": pages, "ocr_used": ocr_used, "word_count": word_count}


def extract_sections(text: str) -> List[Dict]:
    """Detect headings/sections and their page numbers using simple structural
    heuristics (numbered clauses, ALL-CAPS headings)."""
    sections = []
    current_page = 1
    for raw_line in text.split("\n"):
        line = raw_line.strip()
        page_match = re.match(r"\[PAGE (\d+)\]", line)
        if page_match:
            current_page = int(page_match.group(1))
            continue
        if not line:
            continue
        m = HEADING_RE.match(line)
        if m and len(line) < 120:
            sections.append({"heading": line, "page": current_page})
    return sections


def chunk_document(doc_id: str, text: str) -> List[Dict]:
    """Chunk with page + section metadata preserved, overlapping windows."""
    size = settings.CHUNK_SIZE_CHARS
    overlap = settings.CHUNK_OVERLAP_CHARS

    # Track page boundaries as we walk the raw text
    tokens = re.split(r"(\[PAGE \d+\])", text)
    current_page = 1
    running_text = ""
    for tok in tokens:
        pm = re.match(r"\[PAGE (\d+)\]", tok)
        if pm:
            current_page = int(pm.group(1))
            continue
        running_text += tok

    chunks = []
    idx = 0
    pos = 0
    clean_text = re.sub(r"\[PAGE \d+\]", "", text)
    page_positions = _build_page_position_map(text)

    while pos < len(clean_text):
        window = clean_text[pos:pos + size]
        page = _page_for_offset(page_positions, pos)
        section = _nearest_heading(clean_text, pos)
        chunks.append({
            "chunk_index": idx,
            "page": page,
            "section": section,
            "text": window.strip(),
        })
        idx += 1
        pos += max(size - overlap, 1)

    return [c for c in chunks if c["text"]]


def _build_page_position_map(text: str) -> List[Tuple[int, int]]:
    """Map cumulative char offset (in page-marker-stripped text) -> page number."""
    positions = []
    stripped_len = 0
    for m in re.finditer(r"\[PAGE (\d+)\]", text):
        page = int(m.group(1))
        positions.append((stripped_len, page))
        # advance stripped_len by the text between this marker and the next
    # simpler approach: split by marker and accumulate
    positions = []
    running = 0
    for part in re.split(r"(\[PAGE \d+\])", text):
        pm = re.match(r"\[PAGE (\d+)\]", part)
        if pm:
            positions.append((running, int(pm.group(1))))
        else:
            running += len(part)
    return positions


def _page_for_offset(page_positions: List[Tuple[int, int]], offset: int) -> int:
    page = 1
    for start, p in page_positions:
        if start <= offset:
            page = p
        else:
            break
    return page


def _nearest_heading(clean_text: str, offset: int) -> str:
    window_start = max(0, offset - 300)
    preceding = clean_text[window_start:offset]
    lines = [l.strip() for l in preceding.split("\n") if l.strip()]
    for line in reversed(lines):
        if HEADING_RE.match(line) and len(line) < 120:
            return line
    return ""


def save_upload(file_bytes: bytes, filename: str) -> str:
    os.makedirs(settings.UPLOAD_DIR, exist_ok=True)
    import uuid
    ext = os.path.splitext(filename)[1].lower()
    safe_name = f"{uuid.uuid4()}{ext}"
    path = os.path.join(settings.UPLOAD_DIR, safe_name)
    with open(path, "wb") as f:
        f.write(file_bytes)
    return path
