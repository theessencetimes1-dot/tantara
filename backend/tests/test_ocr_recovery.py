import builtins
import io
import time

from reportlab.pdfgen import canvas

from app.ingestion import PdfExtractor


def test_ocr_import_failure_keeps_page_and_returns_recovery_warning(monkeypatch):
    buffer = io.BytesIO()
    pdf = canvas.Canvas(buffer)
    pdf.showPage()
    pdf.save()
    original_import = builtins.__import__

    def broken_ocr_import(name, *args, **kwargs):
        if name in {"pypdfium2", "rapidocr_onnxruntime"}:
            raise RuntimeError("OCR dependency unavailable")
        return original_import(name, *args, **kwargs)

    monkeypatch.setattr(builtins, "__import__", broken_ocr_import)
    pages, warnings = PdfExtractor().extract(buffer.getvalue())
    assert len(pages) == 1
    assert pages[0]["page_number"] == 1
    assert warnings and warnings[0]["page"] == 1
    assert "OCR unavailable or failed" in warnings[0]["warning"]
    assert pages[0]["warnings"] and "manual review required" in pages[0]["warnings"][-1]["warning"]


def scanned_agreement_pdf():
    from PIL import Image, ImageDraw, ImageFont
    from reportlab.lib.utils import ImageReader

    image = Image.new("RGB", (1600, 1000), "white")
    draw = ImageDraw.Draw(image)
    font = ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf", 40)
    draw.text((100, 200), "This agreement is referred to arbitration under", fill="black", font=font)
    draw.text((100, 290), "the Arbitration and Conciliation Act, 1996.", fill="black", font=font)
    draw.text((100, 420), "The seat shall be Mumbai.", fill="black", font=font)
    image_bytes = io.BytesIO()
    image.save(image_bytes, format="PNG")
    image_bytes.seek(0)
    pdf_bytes = io.BytesIO()
    pdf = canvas.Canvas(pdf_bytes, pagesize=(612, 792))
    pdf.drawImage(ImageReader(image_bytes), 0, 0, width=612, height=792)
    pdf.save()
    return pdf_bytes.getvalue()


def test_scanned_agreement_uses_spacing_and_page_geometry():
    pdf_bytes = scanned_agreement_pdf()
    started = time.perf_counter()
    pages, warnings = PdfExtractor().extract(pdf_bytes)
    end_to_end = time.perf_counter() - started
    page = pages[0]
    normalized = " ".join(page["text"].split())
    assert "referred to arbitration under the Arbitration and Conciliation Act, 1996" in normalized
    assert "The seat shall be Mumbai." in normalized
    assert page["ocr_confidence"] > 0.90
    assert not warnings
    import pypdfium2 as pdfium

    rendered_page = pdfium.PdfDocument(pdf_bytes)[0]
    width, height = rendered_page.get_size()
    render_started = time.perf_counter()
    rendered_page.render(scale=PdfExtractor._render_scale(width, height)).to_pil()
    render_cost = time.perf_counter() - render_started
    print(
        f"OCR fixture: confidence={page['ocr_confidence']:.4f}; "
        f"render={render_cost:.3f}s/page; cold extract={end_to_end:.3f}s/page"
    )


def test_ocr_detection_geometry_inserts_interword_spaces():
    detections = [
        ([[0, 0], [25, 0], [25, 10], [0, 10]], "referred", 0.99),
        ([[30, 0], [45, 0], [45, 10], [30, 10]], "to", 0.99),
        ([[50, 0], [95, 0], [95, 10], [50, 10]], "arbitration", 0.99),
        ([[0, 20], [20, 20], [20, 30], [0, 30]], "The", 0.99),
        ([[24, 20], [45, 20], [45, 30], [24, 30]], "seat", 0.99),
    ]
    assert PdfExtractor._ocr_text(detections) == "referred to arbitration\nThe seat"


def test_fused_ocr_tokens_are_recovered_as_legal_words():
    assert PdfExtractor._repair_fused_words("ARBITRATIONAGREEMENT") == "ARBITRATION AGREEMENT"
    repaired = PdfExtractor._repair_fused_words(
        "toarbitrationundertheArbitrationand ConciliationAct, 1996.The seat shall be Mumbai."
    )
    assert "to arbitration under the Arbitration and Conciliation Act, 1996." in repaired
    assert "1996. The seat shall be Mumbai." in repaired
