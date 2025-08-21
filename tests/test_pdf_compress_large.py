import os
import tempfile

import fitz  # PyMuPDF

from utils.pdf_utils import compress_pdf


def _mb(path):
    return os.path.getsize(path) / (1024 * 1024)


def _make_random_pixmap(width=2500, height=2500):
    """
    Create a random RGB pixmap. Random data resists PNG compression, yielding a large file.
    """
    # Each pixel is 3 bytes (RGB)
    samples = os.urandom(width * height * 3)
    # Construct pixmap from raw samples
    pix = fitz.Pixmap(fitz.csRGB, width, height, samples)
    return pix


def _make_pdf_with_big_image(pdf_path: str, w=2500, h=2500):
    pix = _make_random_pixmap(w, h)
    # Save the random image to a temp PNG (so we can insert by filename)
    with tempfile.NamedTemporaryFile(suffix=".png", delete=False) as imf:
        img_path = imf.name
    pix.save(img_path)  # writes PNG
    pix = None

    # Make a 1-page PDF and insert the big image full-bleed
    doc = fitz.open()
    page = doc.new_page(width=612, height=792)  # Letter
    # Put it large on page (bigger than page -> will be scaled)
    rect = fitz.Rect(0, 0, page.rect.width, page.rect.height)
    page.insert_image(rect, filename=img_path, keep_proportion=True)
    doc.save(pdf_path)
    doc.close()
    try:
        os.remove(img_path)
    except OSError:
        pass


def test_compress_pdf_large_random_image(tmp_path):
    src_pdf = tmp_path / "bigimg.pdf"
    _make_pdf_with_big_image(str(src_pdf), w=2500, h=2500)

    original_size = _mb(str(src_pdf))
    assert original_size > 1.0, (
        "Synthetic PDF should be >1MB to make the test meaningful"
    )

    # Compress with stricter settings to ensure a visible reduction
    out_pdf = compress_pdf(
        str(src_pdf), target_mb=9.5, image_dpi_floor=120, jpeg_quality=65
    )
    assert os.path.exists(out_pdf)

    new_size = _mb(out_pdf)

    # Assert: reduced at least 20% (adjust if needed based on your compressor behavior)
    assert new_size < original_size * 0.8, (
        f"Expected at least 20% reduction (was {original_size:.2f} MB -> {new_size:.2f} MB)"
    )
