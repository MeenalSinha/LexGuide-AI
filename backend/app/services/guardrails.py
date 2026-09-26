"""
Guardrails: prompt-injection detection + instruction-layer separation.

Enforces: SYSTEM INSTRUCTIONS -> APPLICATION INSTRUCTIONS -> USER QUERY -> DOCUMENT DATA
Document text is NEVER concatenated into a prompt as anything other than
clearly-delimited, quoted DATA. This module flags suspicious instruction-like
text found inside uploaded documents so the UI can surface a warning, and
strips/neutralizes it before it is used as retrieval context.
"""
import re
from typing import Tuple

INJECTION_PATTERNS = [
    r"ignore (all|any|previous|prior|the) instructions",
    r"disregard (all|any|previous|prior) instructions",
    r"you are now",
    r"system prompt",
    r"reveal (your|the) (system|instructions|prompt)",
    r"act as (if|an?) (admin|root|developer)",
    r"override (your|the) (rules|guidelines|instructions)",
    r"jailbreak",
    r"new instructions:",
    r"do anything now",
]

_COMPILED = [re.compile(p, re.IGNORECASE) for p in INJECTION_PATTERNS]


def scan_for_injection(text: str) -> Tuple[bool, str]:
    """Returns (flagged, note). Never blocks processing - documents are still
    analyzed, but flagged spans are labeled so they can never be treated as
    instructions to the AI."""
    for pattern in _COMPILED:
        if pattern.search(text):
            return True, ("This document contains text that appears to be attempting to manipulate the "
                           "AI's instructions. It has been treated as document content only and was not "
                           "followed as an instruction.")
    return False, ""


def sanitize_for_context(text: str) -> str:
    """Wrap document text so it is unambiguously DATA when included in any
    prompt sent to an LLM provider."""
    flagged, _ = scan_for_injection(text)
    marker = ""
    if flagged:
        marker = "[NOTE: potential embedded instruction detected and neutralized]\n"
    return f"{marker}<document_data>{text}</document_data>"
