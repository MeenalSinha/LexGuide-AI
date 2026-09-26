"""
MODULE 5 — Contract Comparison Engine / Advanced feature 10 — What Changed?
Uses real text diffing (difflib) over clause-aligned segments; every
reported change is anchored to actual text from both documents.
"""
import difflib
import re
from typing import List, Dict
from app.services.analysis_service import split_into_candidate_clauses, classify_clause_category

CHANGE_CATEGORY_FILTERS = ["Financial", "Termination", "Liability", "IP", "Confidentiality", "Obligation", "Deadline"]


def _index_by_heading(clauses: List[Dict]) -> Dict[str, Dict]:
    out = {}
    for c in clauses:
        key = re.sub(r"\s+", " ", c["heading"]).strip().lower() or f"untitled-{len(out)}"
        out[key] = c
    return out


def compare_documents(text_a: str, text_b: str) -> Dict:
    clauses_a = split_into_candidate_clauses(text_a)
    clauses_b = split_into_candidate_clauses(text_b)
    idx_a = _index_by_heading(clauses_a)
    idx_b = _index_by_heading(clauses_b)

    added, removed, modified = [], [], []

    for key, clause_b in idx_b.items():
        if key not in idx_a:
            added.append({
                "heading": clause_b["heading"] or "Untitled clause", "page": clause_b["page"],
                "text": clause_b["text"][:400], "category": classify_clause_category(clause_b["text"], clause_b["heading"]),
            })

    for key, clause_a in idx_a.items():
        if key not in idx_b:
            removed.append({
                "heading": clause_a["heading"] or "Untitled clause", "page": clause_a["page"],
                "text": clause_a["text"][:400], "category": classify_clause_category(clause_a["text"], clause_a["heading"]),
            })

    for key in set(idx_a.keys()) & set(idx_b.keys()):
        clause_a, clause_b = idx_a[key], idx_b[key]
        if clause_a["text"].strip() == clause_b["text"].strip():
            continue
        ratio = difflib.SequenceMatcher(None, clause_a["text"], clause_b["text"]).ratio()
        if ratio > 0.995:
            continue
        category = classify_clause_category(clause_b["text"], clause_b["heading"])
        modified.append({
            "heading": clause_b["heading"] or clause_a["heading"] or "Untitled clause",
            "category": category,
            "previous": clause_a["text"][:400],
            "previous_page": clause_a["page"],
            "new": clause_b["text"][:400],
            "new_page": clause_b["page"],
            "similarity": round(ratio, 3),
            "change_summary": _summarize_change(clause_a["text"], clause_b["text"], category),
            "attention": "HIGH" if category in ("Termination", "Liability", "Financial") and ratio < 0.7 else
                         ("MEDIUM" if ratio < 0.85 else "LOW"),
        })

    return {
        "added": added, "removed": removed, "modified": modified,
        "summary": {
            "added_count": len(added), "removed_count": len(removed), "modified_count": len(modified),
        },
        "filterable_categories": CHANGE_CATEGORY_FILTERS,
    }


def _summarize_change(old: str, new: str, category: str) -> str:
    old_numbers = re.findall(r"\d+\s*(?:day|days|%|percent|months|years)?", old)
    new_numbers = re.findall(r"\d+\s*(?:day|days|%|percent|months|years)?", new)
    if old_numbers and new_numbers and old_numbers != new_numbers:
        return (f"Numeric terms changed from {', '.join(old_numbers[:2])} to {', '.join(new_numbers[:2])} "
                f"in this {category.lower()} clause. Review whether this affects your rights or obligations.")
    diff_ratio = difflib.SequenceMatcher(None, old, new).ratio()
    if diff_ratio < 0.5:
        return f"This {category.lower()} clause was substantially rewritten."
    return f"Minor wording changes were made to this {category.lower()} clause."
