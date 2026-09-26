from app.providers.embedding_provider import TfidfEmbeddingProvider
from app.providers.llm_provider import DemoLLMProvider


def test_embedding_retrieve_ranks_relevant_chunk_first():
    chunks = [
        {"id": "1", "text": "The Landlord shall be responsible for major structural repairs."},
        {"id": "2", "text": "The monthly rent is INR 22,000, due within 5 days of the start of each month."},
        {"id": "3", "text": "Governing law shall be the laws of India."},
    ]
    provider = TfidfEmbeddingProvider()
    results = provider.retrieve("How much is the rent?", chunks, top_k=3)
    assert results[0]["id"] == "2"


def test_llm_answer_question_returns_not_found_with_no_evidence():
    provider = DemoLLMProvider()
    result = provider.answer_question("What is the meaning of life?", [])
    assert result["grounded"] is False
    assert "couldn't find" in result["answer"].lower()


def test_llm_answer_question_grounds_in_evidence():
    provider = DemoLLMProvider()
    evidence = [{"text": "The Tenant shall pay a monthly rent of INR 22,000.", "id": "1"}]
    result = provider.answer_question("How much is the rent?", evidence)
    assert result["grounded"] is True
    assert "22,000" in result["answer"]
