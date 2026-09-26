import os
import tempfile
import pytest

os.environ["DATABASE_URL"] = f"sqlite:///{tempfile.mktemp(suffix='.db')}"
os.environ["UPLOAD_DIR"] = tempfile.mkdtemp()
os.environ["LLM_PROVIDER"] = "demo"

from fastapi.testclient import TestClient  # noqa: E402
from app.main import app  # noqa: E402

DEMO_DIR = os.path.join(os.path.dirname(__file__), "..", "..", "demo", "documents")


@pytest.fixture(scope="session")
def client():
    return TestClient(app)


@pytest.fixture
def upload_employment_v1(client):
    path = os.path.join(DEMO_DIR, "employment_agreement_v1.txt")
    with open(path, "rb") as f:
        r = client.post("/documents/upload", files={"file": ("employment_agreement_v1.txt", f, "text/plain")})
    assert r.status_code == 200
    return r.json()


@pytest.fixture
def upload_employment_v2(client):
    path = os.path.join(DEMO_DIR, "employment_agreement_v2.txt")
    with open(path, "rb") as f:
        r = client.post("/documents/upload", files={"file": ("employment_agreement_v2.txt", f, "text/plain")})
    assert r.status_code == 200
    return r.json()
