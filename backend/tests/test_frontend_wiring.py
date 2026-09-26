"""
Confirms the frontend actually calls every major backend capability -- an
endpoint existing in the API with no frontend caller would be a real gap.
"""
import os

FRONTEND_DIR = os.path.join(os.path.dirname(__file__), "..", "..", "frontend")


def _js():
    with open(os.path.join(FRONTEND_DIR, "app.js"), encoding="utf-8") as f:
        return f.read()


def test_frontend_calls_all_core_endpoints():
    js = _js()
    required_calls = [
        "/documents/upload", "/documents", "/insights", "explain-clause",
        "/questions", "/questions/cross-document", "/compare",
        "/action-plan", "/consultation-brief", "/glossary",
    ]
    for path in required_calls:
        assert path in js, f"frontend never calls {path}"


def test_frontend_wires_brief_export_buttons():
    js = _js()
    assert "consultation-brief/${brief.id}/export" in js
    assert "data-export" in js
