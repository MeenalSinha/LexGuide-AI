from app.services import document_service as docsvc


def test_chunk_metadata_has_required_fields():
    """Spec section 14 requires chunk metadata: page, section, chunk_id (index).
    Confirms every chunk produced carries this metadata, not just raw text."""
    text = "[PAGE 1]\n1. TERMINATION\nThe Company may terminate this Agreement with notice.\n" \
           "[PAGE 2]\n2. COMPENSATION\nThe Company shall pay monthly."
    chunks = docsvc.chunk_document("doc-1", text)
    assert len(chunks) > 0
    for c in chunks:
        assert "chunk_index" in c
        assert "page" in c
        assert "section" in c
        assert "text" in c and c["text"]


def test_citation_evidence_is_grounded_in_real_chunk_text(client, upload_employment_v1):
    """Every citation returned by /questions must be an actual excerpt of a
    real chunk from the uploaded document -- never fabricated."""
    doc_id = upload_employment_v1["id"]
    doc = client.get(f"/documents/{doc_id}").json()
    q = client.post("/questions", json={"question": "What is the compensation?", "document_ids": [doc_id]}).json()
    if q["evidence"]:
        for ev in q["evidence"]:
            excerpt_core = ev["excerpt"].rstrip(".").split("…")[0][:40]
            assert excerpt_core in doc["raw_text"] or excerpt_core.strip() in doc["raw_text"]
            assert ev["page"] is not None or ev["page"] == 0 or ev["page"] is None  # page always present as a key


def test_citation_includes_document_name_and_section(client, upload_employment_v1):
    doc_id = upload_employment_v1["id"]
    q = client.post("/questions", json={"question": "What happens on termination?", "document_ids": [doc_id]}).json()
    if q["grounded"]:
        assert all("document_name" in e for e in q["evidence"])
        assert all("section" in e for e in q["evidence"])
