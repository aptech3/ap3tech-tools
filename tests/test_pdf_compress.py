import os
import shutil

from utils.pdf_utils import compress_pdf


def _size_mb(path):
    return os.path.getsize(path) / (1024 * 1024)


def test_compress_pdf_smoke(tmp_path):
    """
    Smoke test: ensures function runs and reduces or keeps size reasonable.
    To keep the repo light, this test expects a small sample file.
    """
    # Arrange: copy a fixture PDF into tmp (you can add a tiny 1-page scanned sample)
    # Put a small sample fixture under tests/fixtures/sample_scanned.pdf
    fixtures = os.path.join(os.path.dirname(__file__), "fixtures")
    src = os.path.join(fixtures, "sample_scanned.pdf")
    if not os.path.exists(src):
        # Allow skipping if fixture not present in early phases
        import pytest

        pytest.skip("Fixture missing: tests/fixtures/sample_scanned.pdf")

    dst = tmp_path / "sample_scanned.pdf"
    shutil.copy(src, dst)

    # Act
    out = compress_pdf(str(dst))
    assert os.path.exists(out)

    # Assert: size is not larger, and ideally smaller
    assert _size_mb(out) <= _size_mb(str(dst)) + 0.01
