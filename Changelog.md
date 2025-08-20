# Changelog
All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]
### Added
- (placeholder)

### Changed
- (placeholder)

### Fixed
- (placeholder)

---

## [1.0.0] - 2025-08-19
### Added
- **PDF compression utility**: `utils/pdf_utils.py` with `compress_pdf()` to reduce lien notice PDF sizes for Stripe’s **≤10 MB** upload limit (Fixes **#2**).
  - Downscales high‑DPI embedded images (default floor: **144 DPI**).
  - Re-encodes images to JPEG with configurable quality (default **75**).
  - Cleans/deflates objects on save to minimize size.
  - Safe defaults targeting ~**9.5 MB** ceiling; parameters allow stricter settings.
- **CLI entry** for ad‑hoc use:
  - `python -m utils.pdf_utils input.pdf --dpi 144 --quality 75 --target-mb 9.5`
- **Integration point**: helper function `finalize_and_prepare_for_stripe(pdf_path)` (in `main_app.py`) now invokes compression after PDF generation/selection.

### Changed
- None.

### Fixed
- Large lien notices previously exceeding Stripe’s 10 MB limit now compress automatically, avoiding manual splitting/uploads (**#2**).

### Tests
- **Smoke test** `tests/test_pdf_compress.py`:
  - Ensures compression runs and does not increase file size.
  - Uses a small fixture (`tests/fixtures/sample_scanned.pdf`) if available; otherwise skips gracefully.
- **CLI smoke** `tests/test_cli.py`:
  - Verifies `--help` runs successfully.

### Docs
- Added usage notes in code docstrings and CLI help.
- (Recommend) Add a short “PDF Compression” section to `README.md` with CLI and API examples.

### Notes for Upgraders
- No breaking changes; new utility is opt‑in unless wired into your finalize flow.
- For more aggressive size reduction, rerun with `--dpi 120 --quality 65`.

[Unreleased]: https://github.com/aptech3/ap3tech-tools/compare/v1.0.0...HEAD
[1.0.0]: https://github.com/aptech3/ap3tech-tools/releases/tag/v1.0.0
