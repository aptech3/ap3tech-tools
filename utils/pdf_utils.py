# utils/pdf_utils.py
from __future__ import annotations

import os

import fitz  # PyMuPDF

__all__ = ["compress_pdf"]


def _jpeg_bytes_from_pixmap(pix: fitz.Pixmap, quality: int) -> bytes:
    """
    Return JPEG-encoded bytes for a Pixmap across PyMuPDF versions.
    """
    try:
        return pix.tobytes("jpeg", jpg_quality=quality)  # preferred in newer releases
    except TypeError:
        pass
    try:
        return pix.tobytes("jpeg", quality=quality)  # some builds expect 'quality'
    except TypeError:
        pass
    return pix.tobytes("jpeg")


def compress_pdf(
    input_path: str,
    output_path: str | None = None,
    target_mb: float = 9.5,  # kept for API compatibility (not used to loop)
    image_dpi_floor: int = 144,  # rasterization DPI
    jpeg_quality: int = 75,  # JPEG quality (0-100)
) -> str:
    """
    Compress a PDF by rasterizing each page to a JPEG at the chosen DPI.

    Notes:
    - This is robust across PyMuPDF versions and reliably shrinks image-heavy PDFs.
    - It will rasterize vector/text content too. For scanned statements this is fine;
      for vector-heavy PDFs, consider a different path.
    """
    if output_path is None:
        base, ext = os.path.splitext(input_path)
        output_path = f"{base}.compressed{ext}"

    src = fitz.open(input_path)
    dst = fitz.open()

    # Scale factor: DPI / 72 (PDF user units)
    scale = max(image_dpi_floor, 36) / 72.0  # prevent absurdly low DPI
    matrix = fitz.Matrix(scale, scale)

    for page in src:
        # Render page to pixmap at target DPI (no alpha)
        pix = page.get_pixmap(matrix=matrix, alpha=False)

        # Create a matching page in the destination PDF
        new_page = dst.new_page(width=page.rect.width, height=page.rect.height)

        # Insert the rendered page as a single JPEG image
        img_bytes = _jpeg_bytes_from_pixmap(pix, jpeg_quality)
        new_page.insert_image(new_page.rect, stream=img_bytes, keep_proportion=False)

    # Aggressive cleanup on save (mostly irrelevant since dst is new)
    dst.save(
        output_path,
        deflate=True,
        clean=True,
        garbage=4,
        incremental=False,
        pretty=False,
    )
    dst.close()
    src.close()

    # Optional: size check (no retry loop here; caller can adjust DPI/quality)
    try:
        _ = os.path.getsize(output_path)
    except OSError:
        pass

    return output_path
