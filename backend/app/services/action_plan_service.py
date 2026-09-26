"""
MODULE 9 — Action Plan Generator.
Produces categorized, cautious next steps derived from actual clause /
obligation / deadline data - never a legal decision on the user's behalf.
"""
from typing import List, Dict


def generate_action_plan(doc_type: str, clauses: List[Dict], obligations: List[Dict], deadlines: List[Dict],
                          understanding: Dict) -> List[Dict]:
    items = []

    if understanding.get("Effective Date", {}).get("value") == "Not found in document":
        items.append({"category": "VERIFY", "text": "Confirm the effective date of this agreement — it could not be identified automatically."})
    else:
        items.append({"category": "VERIFY", "text": "Confirm the effective date matches your understanding.",
                       "source": understanding["Effective Date"]["source"]})

    high_attention = [c for c in clauses if c.get("attention") == "HIGH"]
    for c in high_attention[:5]:
        items.append({
            "category": "ASK_LAWYER",
            "text": f"Consider having a legal professional review: \u201c{c['heading'] or 'the clause on ' + c['category']}\u201d.",
            "source": {"heading": c["heading"], "page": c.get("page")},
        })

    medium_attention = [c for c in clauses if c.get("attention") == "MEDIUM"]
    for c in medium_attention[:5]:
        items.append({
            "category": "VERIFY",
            "text": f"Review the {c['category'].lower()} provision ({c['heading'] or 'untitled clause'}) before proceeding.",
            "source": {"heading": c["heading"], "page": c.get("page")},
        })

    for d in deadlines[:5]:
        items.append({
            "category": "DO_NOW",
            "text": f"Note the deadline/date reference: \u201c{d['date_text']}\u201d ({d.get('label', '')}).",
            "source": {"heading": d.get("source_heading", ""), "page": d.get("page")},
        })

    payment = understanding.get("Payment / Financial Terms", {})
    if payment.get("value") != "Not found in document":
        items.append({"category": "VERIFY", "text": "Check the payment schedule and confirm the amounts and due dates.",
                       "source": payment.get("source")})

    ip_field = understanding.get("Intellectual Property", {})
    if ip_field.get("value") != "Not found in document":
        items.append({"category": "ASK_OTHER_PARTY",
                       "text": "Ask whether the intellectual property clause applies to work created after termination.",
                       "source": ip_field.get("source")})

    if not obligations:
        items.append({"category": "VERIFY", "text": "No clear obligation statements were automatically detected — review the document manually for responsibilities."})

    items.append({"category": "ASK_LAWYER",
                   "text": "If any provision is unclear or high-stakes for you, have a qualified legal professional review this document before signing."})

    return items
