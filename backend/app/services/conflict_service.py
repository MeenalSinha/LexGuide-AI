"""
MODULE 7 — Multi-Document Q&A / cross-document reasoning.
Advanced: conflict & contradiction detection between two documents.
"""
import re
from typing import List, Dict
from app.services.analysis_service import split_into_candidate_clauses, classify_clause_category

NUMERIC_PATTERN = re.compile(r"(\d+)\s*(day|days|month|months|year|years|%|percent)", re.IGNORECASE)

# Categories where a numeric mismatch across two documents is worth surfacing
# as a potential conflict (e.g. different notice periods for the same kind
# of relationship) -- kept narrow and explainable rather than a black-box score.
CONFLICT_CATEGORIES = ["Termination", "Confidentiality", "Restriction", "Renewal", "Financial"]


def detect_cross_document_conflicts(doc_a_name: str, doc_a_text: str,
                                     doc_b_name: str, doc_b_text: str) -> List[Dict]:
    """Heuristic contradiction detector: for each shared clause category,
    extract the numeric periods/amounts mentioned in each document and flag
    when they differ. This is presented as a pattern-level observation for
    the user to verify -- not a definitive legal conclusion."""
    clauses_a = split_into_candidate_clauses(doc_a_text)
    clauses_b = split_into_candidate_clauses(doc_b_text)

    def numbers_by_category(clauses):
        by_cat = {}
        for c in clauses:
            cat = classify_clause_category(c["text"], c["heading"])
            if cat not in CONFLICT_CATEGORIES:
                continue
            nums = NUMERIC_PATTERN.findall(c["text"])
            if nums:
                by_cat.setdefault(cat, []).append({"heading": c["heading"], "page": c["page"], "numbers": nums})
        return by_cat

    nums_a = numbers_by_category(clauses_a)
    nums_b = numbers_by_category(clauses_b)

    conflicts = []
    for category in CONFLICT_CATEGORIES:
        entries_a = nums_a.get(category, [])
        entries_b = nums_b.get(category, [])
        if not entries_a or not entries_b:
            continue
        values_a = {n for e in entries_a for n in e["numbers"]}
        values_b = {n for e in entries_b for n in e["numbers"]}
        if values_a and values_b and values_a != values_b:
            conflicts.append({
                "category": category,
                "document_a": {"name": doc_a_name, "heading": entries_a[0]["heading"],
                                "page": entries_a[0]["page"], "values": sorted(f"{n[0]} {n[1]}" for n in values_a)},
                "document_b": {"name": doc_b_name, "heading": entries_b[0]["heading"],
                                "page": entries_b[0]["page"], "values": sorted(f"{n[0]} {n[1]}" for n in values_b)},
                "note": f"The two documents state different {category.lower()}-related figures — "
                        f"worth confirming which applies, or whether this is intentional.",
            })
    return conflicts
