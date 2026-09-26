def test_export_brief_as_txt(client, upload_employment_v1):
    brief = client.post("/consultation-brief", json={"document_ids": [upload_employment_v1["id"]]}).json()
    r = client.get(f"/consultation-brief/{brief['id']}/export", params={"format": "txt"})
    assert r.status_code == 200
    assert r.headers["content-type"].startswith("text/plain")
    assert b"LEGAL CONSULTATION BRIEF" in r.content


def test_export_brief_as_docx(client, upload_employment_v1):
    brief = client.post("/consultation-brief", json={"document_ids": [upload_employment_v1["id"]]}).json()
    r = client.get(f"/consultation-brief/{brief['id']}/export", params={"format": "docx"})
    assert r.status_code == 200
    assert "wordprocessingml" in r.headers["content-type"]
    assert len(r.content) > 500  # real docx binary, not empty
    assert r.content[:2] == b"PK"  # docx is a zip container


def test_export_brief_as_pdf(client, upload_employment_v1):
    brief = client.post("/consultation-brief", json={"document_ids": [upload_employment_v1["id"]]}).json()
    r = client.get(f"/consultation-brief/{brief['id']}/export", params={"format": "pdf"})
    assert r.status_code == 200
    assert r.headers["content-type"] == "application/pdf"
    assert r.content[:4] == b"%PDF"


def test_export_brief_rejects_unknown_format(client, upload_employment_v1):
    brief = client.post("/consultation-brief", json={"document_ids": [upload_employment_v1["id"]]}).json()
    r = client.get(f"/consultation-brief/{brief['id']}/export", params={"format": "exe"})
    assert r.status_code == 400
