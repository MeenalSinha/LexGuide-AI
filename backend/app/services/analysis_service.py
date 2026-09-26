"""
MODULE 2 — Document Understanding
MODULE 3 — Plain-Language Explainer (delegates to LLMProvider)
MODULE 4 — Clause Risk Analyzer
Advanced: Obligation Tracker, Deadline Extraction, Document Health Check
"""
import re
from typing import List, Dict
from app.services.document_service import extract_sections
from app.providers.llm_provider import get_llm_provider

CATEGORY_KEYWORDS = {
    "Termination": ["terminat", "notice period", "end this agreement", "cancellation"],
    "Financial": ["payment", "salary", "compensation", "fee", "invoice", "reimburse", "stipend"],
    "Confidentiality": ["confidential", "non-disclosure", "proprietary information"],
    "IP": ["intellectual property", "invention", "copyright", "work product", "patent", "trademark"],
    "Liability": ["liability", "liable", "damages", "limitation of liability"],
    "Indemnification": ["indemnif"],
    "Restriction": ["non-compete", "non-solicit", "shall not engage", "restraint of trade"],
    "Privacy/Data": ["personal data", "privacy", "data protection", "gdpr", "dpdp"],
    "Dispute Resolution": ["arbitration", "dispute", "jurisdiction of the courts", "mediation"],
    "Renewal": ["renew", "extension of term", "automatically renew"],
    "Deadline": ["within \\d+ days", "no later than", "by the \\d", "due date"],
    "Obligation": ["shall", "must", "is required to", "agrees to", "responsible for"],
}

HIGH_ATTENTION_SIGNALS = [
    (r"without (prior )?notice", "Allows action to be taken without prior notice."),
    (r"sole discretion", "Grants one party broad, unilateral discretion."),
    (r"waive[s]? (any|all)", "Involves waiving a right."),
    (r"irrevocable", "Describes an irrevocable commitment."),
    (r"perpetual", "Describes a perpetual (indefinite) obligation or grant."),
    (r"liquidated damages", "Specifies a pre-agreed damages amount."),
    (r"unlimited liability|no limitation of liability", "May involve uncapped liability exposure."),
    (r"non-compete|non-solicit", "Restricts future activity, potentially after the agreement ends."),
    (r"automatic(ally)? renew", "Contract may renew automatically unless action is taken."),
    (r"assign(s|ed|ment)? .* without consent", "May allow assignment of the agreement without consent."),
]

DATE_PATTERNS = [
    r"\b(?:effective|commenc\w*)\s+(?:date|on)\s*[:\-]?\s*([A-Za-z0-9,./\- ]{4,25})",
    r"\bwithin\s+(\d{1,3})\s+(day|days|business days|months|weeks)\b",
    r"\b(\d{1,2}(st|nd|rd|th)?\s+[A-Za-z]+\s+\d{4})\b",
    r"\b([A-Za-z]+\s+\d{1,2},\s*\d{4})\b",
]


AMBIGUOUS_TERMS = [
    "reasonable", "as necessary", "from time to time", "as applicable",
    "where appropriate", "material adverse effect", "best efforts",
    "commercially reasonable", "substantially", "as soon as possible",
    "at its discretion", "as needed", "good faith",
]


def detect_ambiguous_language(text: str) -> List[str]:
    """MODULE D — Ambiguity detection. Flags vague/undefined qualifiers that
    are common sources of contract disputes, without asserting the clause is
    invalid or unenforceable -- just that the wording is imprecise enough to
    warrant a clarifying question."""
    lower = text.lower()
    return sorted({term for term in AMBIGUOUS_TERMS if term in lower})


def classify_clause_category(text: str, heading: str = "") -> str:
    """Classify using both heading (weighted heavily, since it's the clearest
    signal of intent) and body text (weighted lightly), so a clause like
    "6. NON-COMPETE" isn't miscategorized as Termination just because its body
    happens to mention 'termination of this Agreement' in passing."""
    lower = text.lower()
    heading_lower = heading.lower()
    best, best_score = "Informational", 0.0
    for category, keywords in CATEGORY_KEYWORDS.items():
        body_hits = sum(1 for kw in keywords if re.search(kw, lower))
        heading_hits = sum(1 for kw in keywords if re.search(kw, heading_lower))
        score = body_hits + (heading_hits * 5)
        if score > best_score:
            best, best_score = category, score
    # A single incidental body-text mention (score==1) with no heading support
    # is too weak a signal to override "Informational" - avoids classifying an
    # "EFFECTIVE DATE" clause as "Termination" just because it says the
    # agreement continues "until terminated".
    if best_score < 2:
        return "Informational"
    return best


def assess_attention(text: str, category: str) -> Dict:
    lower = text.lower()
    reasons = []
    for pattern, reason in HIGH_ATTENTION_SIGNALS:
        if re.search(pattern, lower):
            reasons.append(reason)

    ambiguous_terms = detect_ambiguous_language(text)
    if ambiguous_terms:
        reasons.append(f"Contains vague/ambiguous wording ({', '.join(ambiguous_terms[:3])}) that could be interpreted differently by each party.")

    if reasons:
        level = "HIGH" if len(reasons) >= 2 else "MEDIUM"
    elif category in ("Termination", "Liability", "Restriction", "Indemnification", "Privacy/Data"):
        level = "MEDIUM"
        reasons.append(f"Clause falls in a category ({category}) that commonly warrants review.")
    else:
        level = "LOW"
        reasons.append("Clause appears routine/informational based on its language.")
    return {"attention": level, "reason": " ".join(reasons), "ambiguous_terms": ambiguous_terms}


def split_into_candidate_clauses(text: str) -> List[Dict]:
    """Split cleaned text into clause-like segments using headings/numbering
    as boundaries, keeping page numbers attached."""
    clean = text
    segments = []
    current_page = 1
    buffer_heading = ""
    buffer_text = []

    def flush():
        joined = "\n".join(buffer_text).strip()
        if joined and len(joined) > 40:
            segments.append({"heading": buffer_heading, "page": current_page, "text": joined})

    for raw_line in clean.split("\n"):
        line = raw_line.strip()
        pm = re.match(r"\[PAGE (\d+)\]", line)
        if pm:
            current_page = int(pm.group(1))
            continue
        if not line:
            continue
        from app.services.document_service import HEADING_RE
        m = HEADING_RE.match(line)
        if m and len(line) < 120:
            flush()
            buffer_heading = line
            buffer_text = []
        else:
            buffer_text.append(line)
    flush()

    # Fallback: if heading detection found almost nothing, split by paragraphs
    if len(segments) < 2:
        paras = [p.strip() for p in re.split(r"\n\s*\n", re.sub(r"\[PAGE \d+\]", "", clean)) if p.strip()]
        segments = [{"heading": f"Paragraph {i+1}", "page": 1, "text": p} for i, p in enumerate(paras) if len(p) > 40]

    return segments


def extract_obligations(clauses: List[Dict]) -> List[Dict]:
    obligations = []
    who_pattern = re.compile(r"\b(the (employee|employer|tenant|landlord|company|contractor|vendor|client|"
                              r"disclosing party|receiving party|licensor|licensee|party))\b", re.IGNORECASE)
    modal_pattern = re.compile(r"\b(shall|must|is required to|agrees to|will be responsible for)\b", re.IGNORECASE)
    when_pattern = re.compile(r"\b(within \d+ (day|days|business days|months)|monthly|annually|"
                               r"by the \d{1,2}(st|nd|rd|th)?|no later than [A-Za-z0-9, ]+|immediately)\b",
                               re.IGNORECASE)
    for clause in clauses:
        text = clause["text"]
        if not modal_pattern.search(text):
            continue
        for sentence in re.split(r"(?<=[.;])\s+", text):
            if not modal_pattern.search(sentence):
                continue
            who_m = who_pattern.search(sentence)
            when_m = when_pattern.search(sentence)
            obligations.append({
                "who": who_m.group(1).title() if who_m else "Not specified",
                "what": sentence.strip()[:280],
                "when": when_m.group(0) if when_m else "Not found in document",
                "condition": "",
                "source_heading": clause["heading"],
                "page": clause["page"],
            })
    return obligations[:40]


def extract_deadlines(clauses: List[Dict]) -> List[Dict]:
    deadlines = []
    for clause in clauses:
        text = clause["text"]
        for pattern in DATE_PATTERNS:
            for m in re.finditer(pattern, text, re.IGNORECASE):
                deadlines.append({
                    "label": clause["heading"] or "Date reference",
                    "date_text": m.group(0).strip(),
                    "source_heading": clause["heading"],
                    "page": clause["page"],
                })
    # de-duplicate
    seen = set()
    unique = []
    for d in deadlines:
        key = (d["date_text"], d["page"])
        if key not in seen:
            seen.add(key)
            unique.append(d)
    return unique[:30]


UNDERSTANDING_FIELDS = [
    "Parties Involved", "Effective Date", "Duration", "Key Obligations",
    "Payment / Financial Terms", "Termination Conditions", "Renewal Conditions",
    "Confidentiality", "Intellectual Property", "Liability", "Indemnification",
    "Dispute Resolution", "Governing Law", "Data/Privacy Obligations",
    "Non-compete / Non-solicitation", "Important Deadlines",
]

FIELD_KEYWORDS = {
    "Parties Involved": ["between", "party", "parties"],
    "Effective Date": ["effective date", "commencement"],
    "Duration": ["term of this agreement", "duration", "period of"],
    "Key Obligations": ["shall", "responsible for", "agrees to"],
    "Payment / Financial Terms": ["payment", "compensation", "salary", "fee"],
    "Termination Conditions": ["terminat"],
    "Renewal Conditions": ["renew"],
    "Confidentiality": ["confidential"],
    "Intellectual Property": ["intellectual property", "invention", "copyright"],
    "Liability": ["liability", "liable"],
    "Indemnification": ["indemnif"],
    "Dispute Resolution": ["arbitration", "dispute", "mediation"],
    "Governing Law": ["governing law", "governed by the laws"],
    "Data/Privacy Obligations": ["personal data", "privacy", "data protection"],
    "Non-compete / Non-solicitation": ["non-compete", "non-solicit"],
    "Important Deadlines": ["within \\d+ days", "no later than", "due date"],
}


def build_document_understanding(doc_type: str, clauses: List[Dict]) -> Dict:
    """Populate the understanding fields ONLY from matched clause text, using
    'Not found in document' rather than guessing (per spec)."""
    result = {}
    for field in UNDERSTANDING_FIELDS:
        keywords = FIELD_KEYWORDS.get(field, [])
        match = None
        for clause in clauses:
            lower = clause["text"].lower()
            if any(re.search(kw, lower) for kw in keywords):
                match = clause
                break
        if match:
            snippet = match["text"][:260].strip()
            result[field] = {
                "value": snippet + ("…" if len(match["text"]) > 260 else ""),
                "source": {"heading": match["heading"], "page": match["page"]},
            }
        else:
            result[field] = {"value": "Not found in document", "source": None}
    return result


def run_document_health_check(text: str, clauses: List[Dict]) -> List[Dict]:
    """MODULE / Advanced feature 9 — structural quality checks (not legal advice)."""
    issues = []
    clean = re.sub(r"\[PAGE \d+\]", "", text)

    # Broken cross references: "Section X" referring to a heading number not present
    refs = set(re.findall(r"[Ss]ection\s+(\d+(?:\.\d+)?)", clean))
    headings_found = set()
    for c in clauses:
        m = re.match(r"^\s*(\d+(\.\d+)?)", c["heading"])
        if m:
            headings_found.add(m.group(1))
    for ref in refs:
        if ref not in headings_found:
            issues.append({
                "type": "Broken cross-reference",
                "detail": f"The document refers to Section {ref}, but a matching section heading could not be found.",
                "severity": "MEDIUM",
            })

    # Placeholders
    placeholders = re.findall(r"\[(?:insert|tbd|xxx|placeholder|fill in)[^\]]*\]", clean, re.IGNORECASE)
    if placeholders:
        issues.append({
            "type": "Empty placeholder",
            "detail": f"Found {len(placeholders)} unfilled placeholder(s) (e.g. '[insert ...]').",
            "severity": "MEDIUM",
        })

    # Duplicate clause headings
    heads = [c["heading"] for c in clauses if c["heading"]]
    dupes = {h for h in heads if heads.count(h) > 1}
    if dupes:
        issues.append({
            "type": "Duplicate clause heading",
            "detail": f"These headings appear more than once: {', '.join(list(dupes)[:5])}.",
            "severity": "LOW",
        })

    # Missing effective date
    if "effective date" not in clean.lower() and "commencement" not in clean.lower():
        issues.append({
            "type": "Missing date",
            "detail": "No effective/commencement date could be identified in the document.",
            "severity": "MEDIUM",
        })

    # Undefined defined-terms (capitalized "Term" in quotes never defined)
    defined = set(re.findall(r'"([A-Z][A-Za-z ]{2,30})"', clean))
    for term in list(defined)[:15]:
        if clean.count(term) <= 1:
            issues.append({
                "type": "Possibly undefined term",
                "detail": f"The term \"{term}\" is introduced but used only once — check whether it is fully defined.",
                "severity": "LOW",
            })

    # Ambiguous wording, aggregated across clauses
    ambiguous_clauses = [c for c in clauses if detect_ambiguous_language(c.get("text", ""))]
    if ambiguous_clauses:
        sample = ambiguous_clauses[0]
        issues.append({
            "type": "Ambiguous wording",
            "detail": f"{len(ambiguous_clauses)} clause(s) contain vague qualifiers (e.g. 'reasonable', "
                      f"'as necessary') that could be interpreted differently by each party — starting with "
                      f"\"{sample.get('heading') or 'an untitled clause'}\".",
            "severity": "LOW",
        })

    # Inconsistent party names: same role referred to by materially different
    # capitalized names/aliases (a common drafting error in template reuse)
    party_mentions = re.findall(r"\b(?:the )?(Employee|Employer|Company|Tenant|Landlord|Contractor|"
                                 r"Vendor|Client|Disclosing Party|Receiving Party|Licensor|Licensee)\b", clean)
    quoted_names = re.findall(r'([A-Z][A-Za-z&.,\' ]{2,40}(?:Pvt\.|Ltd\.|LLC|Inc\.|Corporation))', clean)
    distinct_names = {n.strip() for n in quoted_names}
    if len(distinct_names) > 1:
        # only flag if names look like near-duplicates (drafting inconsistency), not genuinely different entities
        issues.append({
            "type": "Multiple named entities detected",
            "detail": f"Found {len(distinct_names)} distinctly named entities in the document "
                      f"({', '.join(sorted(distinct_names)[:3])}) — confirm these refer to the parties you expect "
                      f"and not an inconsistency from template reuse.",
            "severity": "LOW",
        })

    if not issues:
        issues.append({"type": "No issues detected", "detail": "No structural issues were detected by automated checks.", "severity": "LOW"})

    return issues


def generate_executive_summary(doc_type: str, text: str) -> str:
    provider = get_llm_provider()
    clean = re.sub(r"\[PAGE \d+\]", "", text)
    return provider.summarize_document(clean, doc_type)
