"""
MODULE 10 — Lawyer Preparation Mode.
"""
from typing import List, Dict


def generate_brief(documents: List[Dict], concerns: str = "") -> Dict:
    """documents: list of {filename, doc_type, clauses, obligations, deadlines, understanding, health_issues}"""
    key_areas = []
    questions = []
    important_dates = []
    missing_info = []

    for doc in documents:
        for c in doc["clauses"]:
            if c.get("attention") in ("HIGH", "MEDIUM") and c["category"] not in key_areas:
                key_areas.append(c["category"])
        for d in doc["deadlines"]:
            important_dates.append({"document": doc["filename"], "date": d["date_text"], "context": d.get("label", "")})
        for field, val in doc["understanding"].items():
            if val["value"] == "Not found in document":
                missing_info.append(f"{field} ({doc['filename']})")
        for c in doc["clauses"]:
            if c.get("attention") == "HIGH":
                questions.append(f"Regarding \u201c{c['heading'] or c['category']}\u201d in {doc['filename']}: "
                                  f"what are the practical implications of this provision, and are there any "
                                  f"standard protections I should ask to add?")

    situation_summary = (f"Review of {len(documents)} document(s): " +
                          ", ".join(f"{d['filename']} ({d['doc_type']})" for d in documents) + ".")
    if concerns:
        situation_summary += f" User-stated concern: {concerns}"

    return {
        "matter": documents[0]["doc_type"] if documents else "Document Review",
        "situation_summary": situation_summary,
        "documents_reviewed": [{"filename": d["filename"], "type": d["doc_type"]} for d in documents],
        "key_areas": key_areas[:10],
        "questions": (questions[:8] or ["What should I be aware of before signing this document?"]),
        "important_dates": important_dates[:10],
        "missing_information": missing_info[:10],
        "disclaimer": ("This brief was prepared with AI assistance to help organize information before a "
                        "consultation. It is not legal advice and has not been reviewed by a lawyer."),
    }
