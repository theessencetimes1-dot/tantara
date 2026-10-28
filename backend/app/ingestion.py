"""Safe local extraction, storage and chunk indexing primitives."""

import hashlib
import io
import math
import re
from pathlib import Path

from app.config import get_settings


class DocumentStorage:
    def __init__(self):
        self.root = get_settings().data_dir / "uploads"
        self.root.mkdir(parents=True, exist_ok=True)

    def save(self, data: bytes):
        name = hashlib.sha256(data).hexdigest() + ".bin"
        path = (self.root / name).resolve()
        if path.parent != self.root.resolve():
            raise ValueError("Invalid storage path")
        if not path.exists():
            path.write_bytes(data)
        return str(path)


class PdfExtractor:
    @staticmethod
    def _render_scale(page_width, page_height):
        """Render near 2,000px wide while limiting a single page raster to 12MP."""
        return min(4.0, 2000 / page_width, math.sqrt(12_000_000 / (page_width * page_height)))

    @staticmethod
    def _repair_fused_words(text):
        import wordninja

        def split_token(match):
            token = match.group(0)
            pieces = wordninja.split(token.lower())
            if len(pieces) < 2:
                return token
            if token.isupper():
                return " ".join(piece.upper() for piece in pieces)
            if token[0].isupper():
                pieces[0] = pieces[0].capitalize()
            return " ".join(pieces)

        text = re.sub(r"(?<=[a-z])(?=[A-Z])", " ", text)
        text = re.sub(r"(?<=[.!?])(?=[A-Z])", " ", text)
        return re.sub(r"[A-Za-z]{6,}", split_token, text)

    @staticmethod
    def _ocr_text(detections):
        """Join OCR detections by their page geometry and repair common fused words."""
        rows = []
        for box, text, _confidence in detections or []:
            points = [(float(point[0]), float(point[1])) for point in box]
            left = min(point[0] for point in points)
            right = max(point[0] for point in points)
            top = min(point[1] for point in points)
            bottom = max(point[1] for point in points)
            rows.append((top, bottom, left, right, str(text).strip()))
        rows.sort(key=lambda row: ((row[0] + row[1]) / 2, row[2]))
        lines = []
        for item in rows:
            top, bottom, *_ = item
            center = (top + bottom) / 2
            match = next(
                (
                    line
                    for line in reversed(lines)
                    if abs(center - line["center"]) <= 0.45 * max(bottom - top, line["height"])
                ),
                None,
            )
            if match is None:
                lines.append({"center": center, "height": bottom - top, "items": [item]})
            else:
                match["items"].append(item)
                match["center"] = sum((row[0] + row[1]) / 2 for row in match["items"]) / len(match["items"])
                match["height"] = max(row[1] - row[0] for row in match["items"])

        output = []
        for line in sorted(lines, key=lambda row: row["center"]):
            line_items = sorted(line["items"], key=lambda row: row[2])
            text_parts = []
            previous = None
            for item in line_items:
                if previous is not None:
                    gap = item[2] - previous[3]
                    # RapidOCR may return words as separate boxes; keep their visual gap.
                    if gap > max(1.0, line["height"] * 0.06):
                        text_parts.append(" ")
                text_parts.append(item[4])
                previous = item
            output.append(PdfExtractor._repair_fused_words("".join(text_parts)))
        return "\n".join(output)

    def extract(self, data):
        from pypdf import PdfReader

        reader = PdfReader(io.BytesIO(data))
        pages = []
        warnings = []
        pdfium_document = None
        ocr_engine = None
        for i, page in enumerate(reader.pages, 1):
            content = page.extract_text() or ""
            conf = None
            page_warnings = []
            if len(content.strip()) < 20:
                try:
                    import pypdfium2 as pdfium
                    from rapidocr_onnxruntime import RapidOCR

                    if pdfium_document is None:
                        pdfium_document = pdfium.PdfDocument(data)
                    if ocr_engine is None:
                        ocr_engine = RapidOCR()
                    pdf_page = pdfium_document[i - 1]
                    page_width, page_height = pdf_page.get_size()
                    scale = self._render_scale(page_width, page_height)
                    bmp = pdf_page.render(scale=scale).to_pil()
                    result, _ = ocr_engine(bmp)
                    content = self._ocr_text(result)
                    conf = (sum(x[2] for x in result) / len(result)) if result else 0
                except Exception as exc:
                    warning = {"page": i, "warning": f"OCR unavailable or failed: {type(exc).__name__}"}
                    warnings.append(warning)
                    page_warnings.append(warning)
            if not content.strip():
                warning = {"page": i, "warning": "No usable text; manual review required"}
                warnings.append(warning)
                page_warnings.append(warning)
            pages.append(
                {
                    "page_number": i,
                    "text": content,
                    "ocr_confidence": conf,
                    "warnings": page_warnings,
                }
            )
        return pages, warnings


class DocxExtractor:
    def extract(self, data):
        from docx import Document

        d = Document(io.BytesIO(data))
        return [
            {"page_number": 1, "text": "\n".join(p.text for p in d.paragraphs), "ocr_confidence": None}
        ], []


class TextMarkdownExtractor:
    def extract(self, data):
        return [{"page_number": 1, "text": data.decode("utf8", errors="replace"), "ocr_confidence": None}], []


class OcrFallback(PdfExtractor):
    pass


class DocumentExtractor:
    def extract(self, filename, data):
        ext = Path(filename).suffix.lower()
        if ext == ".pdf":
            return PdfExtractor().extract(data)
        if ext == ".docx":
            return DocxExtractor().extract(data)
        if ext in {".txt", ".md"}:
            return TextMarkdownExtractor().extract(data)
        raise ValueError("Supported file types: PDF, DOCX, TXT, MD")


def extract(filename, data):
    pages, warnings = DocumentExtractor().extract(filename, data)
    return "\n".join(p["text"] for p in pages)


def ingest(filename, data, title, document_type="template", jurisdiction="India", source_label=None):
    """Legacy entry point retained for callers; new API persists async jobs."""
    pages, warnings = DocumentExtractor().extract(filename, data)
    return {
        "text": "\n".join(p["text"] for p in pages),
        "pages": pages,
        "warnings": warnings,
        "content_hash": hashlib.sha256(data).hexdigest(),
    }
