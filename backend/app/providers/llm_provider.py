"""
LLMProvider interface + implementations.

The rest of the app never talks to a model SDK directly - it calls
LLMProvider.explain_clause() / .answer_question() / .summarize(), so the
underlying model can be swapped (Anthropic, OpenAI, Gemini, local model)
without touching business logic.

DemoLLMProvider is deterministic and offline: it uses templated,
rule-based generation so the entire product is demonstrable without any
API key. AnthropicLLMProvider is a thin real implementation used when
ANTHROPIC_API_KEY is configured.
"""
from abc import ABC, abstractmethod
from functools import lru_cache
from typing import List, Dict


class LLMProvider(ABC):
    @abstractmethod
    def plain_language(self, clause_text: str, category: str) -> Dict:
        ...

    @abstractmethod
    def summarize_document(self, text: str, doc_type: str) -> str:
        ...

    @abstractmethod
    def answer_question(self, question: str, evidence_chunks: List[Dict]) -> Dict:
        ...


class DemoLLMProvider(LLMProvider):
    """Deterministic, offline provider used by default (LLM_PROVIDER=demo)."""

    CAUTIOUS_PHRASES = {
        "termination": "This provision affects how and when the agreement can end.",
        "liability": "This provision affects who bears responsibility if something goes wrong.",
        "confidentiality": "This provision restricts what information can be shared.",
        "ip": "This provision affects ownership of work product or inventions.",
        "financial": "This provision affects money owed or paid under the agreement.",
        "restriction": "This provision limits what you can do, including after the agreement ends.",
        "dispute resolution": "This provision affects how disagreements are resolved.",
        "privacy/data": "This provision affects how personal or business data is handled.",
    }

    def plain_language(self, clause_text: str, category: str) -> Dict:
        cat_key = category.lower()
        why = self.CAUTIOUS_PHRASES.get(cat_key, "This provision may create a right or obligation worth understanding clearly.")
        simple = self._simplify(clause_text)
        return {
            "simple": simple,
            "why_it_matters": why,
            "questions": self._default_questions(cat_key),
        }

    def summarize_document(self, text: str, doc_type: str) -> str:
        first = text.strip().split("\n")[0][:180] if text.strip() else ""
        return (f"This appears to be a {doc_type.lower()}. It sets out the rights and obligations of the "
                f"parties involved. Automatically generated from document text; verify against the original. "
                f"Opening line: \u201c{first}\u2026\u201d" if first else
                f"This appears to be a {doc_type.lower()}. Review the extracted sections below for details.")

    def answer_question(self, question: str, evidence_chunks: List[Dict]) -> Dict:
        if not evidence_chunks:
            return {
                "answer": "I couldn't find this information in the uploaded documents.",
                "grounded": False,
            }
        top = evidence_chunks[0]
        snippet = top["text"][:400].strip()
        answer = (f"Based on the uploaded document, the relevant passage states: \u201c{snippet}"
                  f"{'…' if len(top['text']) > 400 else ''}\u201d This section appears most relevant to your "
                  f"question about \u201c{question.strip().rstrip('?')}\u201d. Review the source clause for the exact wording.")
        return {"answer": answer, "grounded": True}

    @staticmethod
    def _simplify(text: str) -> str:
        t = text.strip()
        if len(t) > 320:
            t = t[:320].rsplit(" ", 1)[0] + "…"
        return f"In plain terms: {t}"

    @staticmethod
    def _default_questions(cat_key: str) -> List[str]:
        base = ["Does this apply after the agreement ends?", "Are there any exceptions?", "Is there a time limit?"]
        extra = {
            "termination": ["How much notice is required?", "What counts as a valid reason for termination?"],
            "financial": ["When exactly is payment due?", "What happens if payment is late?"],
            "confidentiality": ["What information is excluded from confidentiality?", "How long does this obligation last?"],
            "ip": ["Does this cover work created before the agreement?", "Who owns jointly created work?"],
        }
        return base + extra.get(cat_key, [])


class AnthropicLLMProvider(LLMProvider):
    """
    Real provider using the Anthropic API. Only used when LLM_PROVIDER=anthropic
    and ANTHROPIC_API_KEY is set. Falls back to demo behavior on any error so
    the product never breaks mid-demo.
    """
    def __init__(self, api_key: str):
        self.api_key = api_key
        self._fallback = DemoLLMProvider()

    def plain_language(self, clause_text: str, category: str) -> Dict:
        try:
            import anthropic
            client = anthropic.Anthropic(api_key=self.api_key)
            prompt = (
                "You are a cautious legal-information assistant. You are NOT a lawyer and must not give "
                "legal advice or definitive conclusions. Given the clause below, produce JSON with keys "
                "'simple' (plain-language explanation), 'why_it_matters', and 'questions' (3-5 questions "
                "the reader should consider). Use cautious language such as 'may', 'could', 'consider asking'. "
                f"Clause category: {category}\nClause text:\n{clause_text[:2000]}\n"
                "Respond ONLY with JSON, no other text."
            )
            resp = client.messages.create(
                model="claude-sonnet-4-6", max_tokens=600,
                messages=[{"role": "user", "content": prompt}],
            )
            import json
            text = "".join(b.text for b in resp.content if getattr(b, "type", "") == "text")
            return json.loads(text)
        except Exception:
            return self._fallback.plain_language(clause_text, category)

    def summarize_document(self, text: str, doc_type: str) -> str:
        try:
            import anthropic
            client = anthropic.Anthropic(api_key=self.api_key)
            prompt = (f"Summarize this {doc_type} in 3-4 neutral sentences, no legal conclusions, "
                       f"no advice, only what the document states:\n{text[:6000]}")
            resp = client.messages.create(model="claude-sonnet-4-6", max_tokens=300,
                                           messages=[{"role": "user", "content": prompt}])
            return "".join(b.text for b in resp.content if getattr(b, "type", "") == "text")
        except Exception:
            return self._fallback.summarize_document(text, doc_type)

    def answer_question(self, question: str, evidence_chunks: List[Dict]) -> Dict:
        if not evidence_chunks:
            return {"answer": "I couldn't find this information in the uploaded documents.", "grounded": False}
        try:
            import anthropic
            client = anthropic.Anthropic(api_key=self.api_key)
            context = "\n---\n".join(c["text"][:800] for c in evidence_chunks[:4])
            prompt = (
                "Answer strictly using the CONTEXT below. Do not use outside knowledge. If the context does "
                "not contain the answer, say you couldn't find it in the uploaded documents. Be neutral and "
                "cautious; you are not a lawyer.\n"
                f"CONTEXT:\n{context}\n\nQUESTION: {question}\nANSWER:"
            )
            resp = client.messages.create(model="claude-sonnet-4-6", max_tokens=500,
                                           messages=[{"role": "user", "content": prompt}])
            answer = "".join(b.text for b in resp.content if getattr(b, "type", "") == "text")
            return {"answer": answer, "grounded": True}
        except Exception:
            return self._fallback.answer_question(question, evidence_chunks)


@lru_cache(maxsize=1)
def get_llm_provider() -> LLMProvider:
    """Reuse the configured provider and its fallback client across requests."""
    from app.core.config import settings
    if settings.LLM_PROVIDER == "anthropic" and settings.ANTHROPIC_API_KEY:
        return AnthropicLLMProvider(settings.ANTHROPIC_API_KEY)
    return DemoLLMProvider()
