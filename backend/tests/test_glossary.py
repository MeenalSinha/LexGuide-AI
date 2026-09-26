def test_list_glossary_terms(client):
    r = client.get("/documents/glossary/terms")
    assert r.status_code == 200
    terms = r.json()["terms"]
    assert "indemnification" in terms
    assert "non-compete" in terms


def test_explain_known_term_found_in_document(client, upload_employment_v1):
    doc_id = upload_employment_v1["id"]
    r = client.get(f"/documents/{doc_id}/glossary/confidentiality")
    assert r.status_code == 200
    body = r.json()
    assert body["found_in_document"] is True
    assert "confidential" in body["document_context"].lower()
    assert "not legal advice" in body["note"].lower()


def test_explain_term_not_present_in_document(client, upload_employment_v1):
    doc_id = upload_employment_v1["id"]
    r = client.get(f"/documents/{doc_id}/glossary/force%20majeure")
    assert r.status_code == 200
    body = r.json()
    assert body["found_in_document"] is False
    assert body["document_context"] == "Not found in document"


def test_explain_unknown_term_returns_404(client, upload_employment_v1):
    doc_id = upload_employment_v1["id"]
    r = client.get(f"/documents/{doc_id}/glossary/not-a-real-legal-term-xyz")
    assert r.status_code == 404


def test_glossary_term_for_missing_document_returns_404(client):
    r = client.get("/documents/00000000-0000-0000-0000-000000000000/glossary/liability")
    assert r.status_code == 404
