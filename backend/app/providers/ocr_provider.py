"""
OCRProvider interface.

The prototype detects scanned/empty-text PDF pages and flags them rather
than shipping a heavy Tesseract binary dependency into this environment.
NullOCRProvider marks such pages clearly so the UI can show:
"OCR-derived text — verify against original document." once a real OCR
backend (Tesseract / cloud OCR) is wired in. Swapping in a real OCR engine
only requires implementing extract_text() below - no caller changes.
"""
from abc import ABC, abstractmethod


class OCRProvider(ABC):
    @abstractmethod
    def extract_text(self, image_bytes: bytes) -> str:
        ...


class NullOCRProvider(OCRProvider):
    def extract_text(self, image_bytes: bytes) -> str:
        return "[Scanned page detected — OCR engine not configured in this environment. " \
               "Connect a Tesseract/cloud OCR backend to extract text from this page.]"


def get_ocr_provider() -> OCRProvider:
    return NullOCRProvider()
