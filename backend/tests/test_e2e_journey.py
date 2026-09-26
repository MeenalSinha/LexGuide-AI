def test_health(client):
    r = client.get("/health")
    assert r.status_code == 200
    assert r.json()["status"] == "ok"


def test_full_journey_upload_analyze_ask_compare_plan_brief(client, upload_employment_v1, upload_employment_v2):
    d1, d2 = upload_employment_v1, upload_employment_v2

    # Insights
    ins = client.get(f"/documents/{d1['id']}/insights")
    assert ins.status_code == 200
    body = ins.json()
    assert body["analytics"]["clauses_detected"] > 0
    assert "executive_summary" in body

    # Explain a clause
    clause_id = body["clauses"][0]["id"]
    explain = client.post(f"/documents/{d1['id']}/explain-clause/{clause_id}")
    assert explain.status_code == 200
    assert "simple" in explain.json()["plain_language"]

    # Ask
    q = client.post("/questions", json={"question": "What happens if I terminate this agreement?",
                                          "document_ids": [d1["id"]]})
    assert q.status_code == 200
    assert q.json()["evidence"] or q.json()["grounded"] is False

    # Unanswerable question -> must not hallucinate
    q2 = client.post("/questions", json={"question": "What is the capital of France?", "document_ids": [d1["id"]]})
    assert q2.status_code == 200
    assert q2.json()["grounded"] is False
    assert "couldn't find" in q2.json()["answer"].lower()

    # Compare
    cmp = client.post("/compare", json={"document_a_id": d1["id"], "document_b_id": d2["id"]})
    assert cmp.status_code == 200
    assert cmp.json()["summary"]["modified_count"] > 0

    # Action plan
    ap = client.post("/action-plan", json={"document_id": d1["id"]})
    assert ap.status_code == 200
    assert "grouped" in ap.json()

    # Consultation brief
    brief = client.post("/consultation-brief", json={"document_ids": [d1["id"]], "concerns": "test concern"})
    assert brief.status_code == 200
    assert "disclaimer" in brief.json()

    # Export path (brief retrievable by id)
    brief_id = brief.json()["id"]
    got = client.get(f"/consultation-brief/{brief_id}")
    assert got.status_code == 200


def test_list_and_delete_document(client, upload_employment_v1):
    doc_id = upload_employment_v1["id"]
    listing = client.get("/documents")
    assert any(d["id"] == doc_id for d in listing.json())

    deleted = client.delete(f"/documents/{doc_id}")
    assert deleted.status_code == 200
    assert deleted.json()["deleted"] is True

    missing = client.get(f"/documents/{doc_id}")
    assert missing.status_code == 404
