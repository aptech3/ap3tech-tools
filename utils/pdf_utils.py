# utils/pdf_utils.py
from __future__ import annotations
import io
import os
import fitz  # PyMuPDF

def compress_pdf(
    input_path: str,
    output_path: str | None = None,
    target_mb: float = 9.5,
    image_dpi_floor: int = 144,
    jpeg_quality: int = 75,
) -> str:
    """
    Compress a PDF by recompressing embedded images and cleaning objects.
    - image_dpi_floor: minimum DPI to keep (downscale higher-resolution images)
    - jpeg_quality: 0-100 (lower = smaller)
    Returns the output path.
    """
    if output_path is None:
        base, ext = os.path.splitext(input_path)
        output_path = f"{base}.compressed{ext}"

    # Open original
    doc = fitz.open(input_path)

    # Re-encode images page-by-page
    for page_index in range(len(doc)):
        page = doc[page_index]
        img_list = page.get_images(full=True)
        if not img_list:
            continue

        for img in img_list:
            xref = img[0]
            # Extract original image
            pix = fitz.Pixmap(doc, xref)
            if pix.n > 4:
                # Convert CMYK/other to RGB
                pix = fitz.Pixmap(fitz.csRGB, pix)

            # Heuristic: downscale if over our DPI threshold relative to page size
            # Compute size on page (points) & image pixel size
            try:
                rects = page.get_image_bbox(xref)
            except Exception:
                rects = None

            if rects:
                rect = rects
                # Points to inches (72 pt per inch)
                width_in = rect.width / 72.0
                height_in = rect.height / 72.0
                # Avoid div zero
                width_in = max(width_in, 0.01)
                height_in = max(height_in, 0.01)
                dpi_x = pix.width / width_in
                dpi_y = pix.height / height_in
                # If image is over threshold, compute scale
                scale = min(image_dpi_floor / dpi_x, image_dpi_floor / dpi_y, 1.0)
            else:
                # If bounding box not available, conservatively recompress at same size
                scale = 1.0

            # Scale if beneficial
            if scale < 1.0:
                new_w = max(int(pix.width * scale), 1)
                new_h = max(int(pix.height * scale), 1)
                pix = fitz.Pixmap(pix, 0)  # make sure it's a simple pixmap
                pix = pix.resize(new_w, new_h)

            # Encode to JPEG to reduce size
            img_bytes = pix.tobytes("jpg", quality=jpeg_quality)
            new_xref = doc.insert_image(
                page.rect,  # temporary insertion
                stream=img_bytes,
                keep_proportion=True,
                overlay=True
            )
            # Replace references (clean-up: remove old object)
            doc._delete_object(xref)

    # Save with garbage collection and object compression
    # deflate=True enables stream compression; garbage=4 is aggressive cleanup
    doc.save(
        output_path,
        deflate=True,
        garbage=4,
        clean=True,
        incremental=False,
        pretty=False,
    )
    doc.close()

    # If still over target, advise caller (we keep file, but return path)
    size_mb = os.path.getsize(output_path) / (1024 * 1024)
    if size_mb > target_mb:
        # We could allow the caller to retry with lower jpeg_quality or dpi.
        pass

    return output_path

if __name__ == "__main__":
    import argparse
    p = argparse.ArgumentParser(description="Compress a PDF for Stripe (≤10MB).")
    p.add_argument("input", help="Path to source PDF")
    p.add_argument("-o", "--output", help="Path to output PDF")
    p.add_argument("--target-mb", type=float, default=9.5)
    p.add_argument("--dpi", type=int, default=144)
    p.add_argument("--quality", type=int, default=75)
    args = p.parse_args()
    out = compress_pdf(args.input, args.output, args.target_mb, args.dpi, args.quality)
    print(f"Compressed saved -> {out}")
