"""
MODULE 8 — Legal Term Explainer.

A small curated glossary of common contract terms, combined with the same
hybrid retrieval used elsewhere so a term's explanation is grounded in how
it actually appears in THIS document (not just a generic dictionary
definition presented as if it were legal advice).
"""
import re
from typing import Dict, List, Optional

GLOSSARY: Dict[str, Dict[str, str]] = {
    "indemnification": {
        "simple": "One party may be required to cover certain losses, damages, or claims that the other party experiences, often arising from a breach of the agreement.",
        "example": "If a vendor's product causes a data breach, an indemnification clause might require the vendor to cover the resulting legal costs.",
        "why_it_matters": "It determines who bears financial responsibility when something goes wrong, and can be uncapped or limited.",
    },
    "liability": {
        "simple": "The legal responsibility one party has for losses, damages, or harm connected to the agreement.",
        "example": "A 'limitation of liability' clause might cap how much a company has to pay if something goes wrong.",
        "why_it_matters": "It affects how much financial risk you're exposed to if a dispute arises.",
    },
    "confidentiality": {
        "simple": "An obligation to keep certain information private and not share it with others.",
        "example": "An employee agreeing not to disclose a company's trade secrets, even after leaving the job.",
        "why_it_matters": "It can restrict what you're allowed to say or share, sometimes indefinitely.",
    },
    "non-compete": {
        "simple": "A restriction on working for a competitor or starting a competing business, usually for a set time and geographic area.",
        "example": "Not being allowed to join a rival company for 12 months after leaving your job.",
        "why_it_matters": "It can limit your future employment options — enforceability varies significantly by jurisdiction.",
    },
    "non-solicitation": {
        "simple": "A restriction on recruiting a former employer's employees or clients.",
        "example": "Agreeing not to hire your former coworkers for a period after you leave.",
        "why_it_matters": "It can limit who you're allowed to hire or approach for business after the agreement ends.",
    },
    "arbitration": {
        "simple": "A private process for resolving disputes outside of court, usually with a neutral third party deciding the outcome.",
        "example": "Instead of suing in court, both parties present their case to an arbitrator whose decision is typically binding.",
        "why_it_matters": "It often means giving up the right to a jury trial or class-action lawsuit.",
    },
    "governing law": {
        "simple": "The state or country's laws that will be used to interpret and enforce the agreement.",
        "example": "A contract stating it is 'governed by the laws of India' means Indian law applies to disputes.",
        "why_it_matters": "It determines which legal system and rules apply if there's ever a disagreement.",
    },
    "intellectual property": {
        "simple": "Creations of the mind — inventions, designs, written work, code, or brands — that can be legally owned.",
        "example": "Code written by an employee during their job often becomes the company's intellectual property.",
        "why_it_matters": "It determines who owns work you create, sometimes even after the agreement ends.",
    },
    "termination": {
        "simple": "The ending of the agreement, and the conditions under which either party can end it.",
        "example": "A clause allowing either party to end the contract with 30 days' written notice.",
        "why_it_matters": "It affects how easily you (or the other party) can exit the agreement, and under what conditions.",
    },
    "renewal": {
        "simple": "The continuation of an agreement beyond its original end date, often automatically unless action is taken.",
        "example": "A lease that automatically renews for another year unless either party gives 30 days' notice.",
        "why_it_matters": "Automatic renewal clauses can extend obligations you may have intended to end.",
    },
    "waiver": {
        "simple": "Giving up a right or claim you would otherwise be entitled to.",
        "example": "Agreeing to waive the right to sue for certain types of damages.",
        "why_it_matters": "Once waived, a right can be very difficult or impossible to reclaim later.",
    },
    "force majeure": {
        "simple": "A clause that excuses a party from fulfilling obligations due to extraordinary events beyond their control (natural disasters, war, etc.).",
        "example": "A supplier not being penalized for late delivery due to a natural disaster.",
        "why_it_matters": "It affects who bears the risk of major unforeseen disruptions.",
    },
    "severability": {
        "simple": "A clause stating that if one part of the agreement is found invalid, the rest of the agreement still stands.",
        "example": "If a court strikes down one clause as unenforceable, the rest of the contract remains valid.",
        "why_it_matters": "It protects the overall agreement from collapsing due to one problematic clause.",
    },
    "assignment": {
        "simple": "The transfer of rights or obligations under the agreement to another party.",
        "example": "A company selling its business and transferring its contracts to the buyer.",
        "why_it_matters": "It affects whether your agreement could end up being enforced by or against a different party than you originally signed with.",
    },
    "dispute resolution": {
        "simple": "The agreed-upon process for resolving disagreements between the parties.",
        "example": "A clause requiring mediation before either party can go to court.",
        "why_it_matters": "It shapes how, where, and through what process disagreements get resolved.",
    },
}


def list_terms() -> List[str]:
    return sorted(GLOSSARY.keys())


def explain_term(term: str, document_text: str) -> Optional[Dict]:
    key = term.strip().lower()
    entry = GLOSSARY.get(key)
    if not entry:
        return None

    # Find the most relevant sentence(s) in the document mentioning this term
    clean = re.sub(r"\[PAGE \d+\]", "", document_text)
    sentences = re.split(r"(?<=[.;])\s+", clean)
    context_sentences = [s.strip() for s in sentences if key.split()[0] in s.lower()][:2]
    document_context = " ".join(context_sentences) if context_sentences else "Not found in document"

    return {
        "term": term,
        "simple": entry["simple"],
        "example": entry["example"],
        "why_it_matters": entry["why_it_matters"],
        "document_context": document_context,
        "found_in_document": bool(context_sentences),
        "note": "This is a general definition, not legal advice. How this term applies in your specific document may differ.",
    }
