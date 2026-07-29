import os

import fitz
import pytesseract

from pdf2image import convert_from_path

configured_tesseract = os.getenv("TESSERACT_CMD", "").strip()
if configured_tesseract:
    pytesseract.pytesseract.tesseract_cmd = configured_tesseract


def _configured_poppler_path():
    configured_path = os.getenv("POPPLER_PATH", "").strip()
    return configured_path or None


def extract_text(pdf_path):
    text = ""

    with fitz.open(pdf_path) as doc:
        for page in doc:
            text += page.get_text()

    if text.strip():
        return text

    images = convert_from_path(
        pdf_path,
        poppler_path=_configured_poppler_path(),
    )

    return "".join(
        pytesseract.image_to_string(image)
        for image in images
    )
