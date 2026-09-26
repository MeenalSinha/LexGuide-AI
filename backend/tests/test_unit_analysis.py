from app.services import document_service as docsvc
from app.services import analysis_service as analysis


SAMPLE = """[PAGE 1]
EMPLOYMENT AGREEMENT

1. TERMINATION
The Company may terminate this Agreement without prior notice in cases of misconduct.

2. NON-COMPETE
The Employee shall not engage in any competing business within 12 months after termination.

[PAGE 2]
3. COMPENSATION
The Company shall pay the Employee within 5 days of month end.
"""


def test_chunking_preserves_pages():
    chunks = docsvc.chunk_document("doc1", SAMPLE)
    assert len(chunks) > 0
    pages = {c["page"] for c in chunks}
    assert 1 in pages


def test_detect_doc_type_employment():
    assert docsvc.detect_doc_type("Employment_Agreement.pdf", "") == "Employment Agreement"


def test_split_into_candidate_clauses():
    clauses = analysis.split_into_candidate_clauses(SAMPLE)
    headings = [c["heading"] for c in clauses]
    assert any("TERMINATION" in h for h in headings)
    assert any("NON-COMPETE" in h for h in headings)


def test_classify_clause_category_heading_priority():
    # Body mentions "termination" but heading is NON-COMPETE -> should classify as Restriction, not Termination
    text = "The Employee shall not engage in any competing business within 12 months after termination of this Agreement."
    category = analysis.classify_clause_category(text, heading="2. NON-COMPETE")
    assert category == "Restriction"


def test_assess_attention_flags_without_notice():
    text = "The Company may terminate this Agreement without prior notice in cases of misconduct."
    result = analysis.assess_attention(text, "Termination")
    assert result["attention"] in ("MEDIUM", "HIGH")
    assert "notice" in result["reason"].lower()


def test_extract_obligations_finds_shall_statements():
    clauses = analysis.split_into_candidate_clauses(SAMPLE)
    obligations = analysis.extract_obligations(clauses)
    assert len(obligations) > 0
    assert any("pay" in o["what"].lower() or "shall" in o["what"].lower() for o in obligations)


def test_extract_deadlines_finds_day_references():
    clauses = analysis.split_into_candidate_clauses(SAMPLE)
    deadlines = analysis.extract_deadlines(clauses)
    assert any("5 days" in d["date_text"] for d in deadlines)


def test_health_check_flags_placeholder():
    text = "This Agreement is between [INSERT PARTY NAME] and the Company."
    issues = analysis.run_document_health_check(text, [])
    assert any(i["type"] == "Empty placeholder" for i in issues)


def test_health_check_no_issues_on_clean_text():
    text = "Effective Date: January 1, 2026. This is a simple clean document with no placeholders."
    issues = analysis.run_document_health_check(text, [])
    assert any(i["type"] == "No issues detected" for i in issues)
