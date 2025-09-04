# Changelog
All notable changes to this project will be documented in this file.
The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]
### Added
- EVG Splitter CLI: run `python evg_splitter.py input.pdf` (or multiple PDFs/dirs) with optional `-o OUTPUT_DIR` and `-r` for recursive directory scanning.
- Mulligan contract redactor: `python contract_redactor.py file.pdf` redacts EIN and bank routing/account numbers on page 5. Options: `-p` (page), `-o` (output dir), `-q` (quiet).
 - GUI: EVG Splitter auto-detects Mulligan Funding contracts and saves a redacted copy of the Contract (page 5 masked) alongside the split files.

### Changed
- (placeholder)

### Fixed
- (placeholder)

---
## [1.5.0] - 2025-09-04
### Added
- PyQt app: In‑app PDF preview for AI Statement Analysis summary PDFs, with zoom controls and page navigation. Adds “Preview Here” action from completion dialog.
- PyQt app: AI completion dialog lists output folders and allows opening them; added auto‑open first output folder option.
- Build CI: GitHub Actions workflow to build Windows and macOS single‑file binaries with PyInstaller (`.github/workflows/build.yml`).
- Build env: `requirements-build.txt` to stabilize CI packaging.

### Changed
- AI analysis: default model set to `gpt-4o-mini` for availability and cost; added 90s request timeouts and a robust wrapper compatible with OpenAI SDK 1.x and legacy.
- README updates: document PyQt entry point (`main_app_pyqt.py`), packaged builds for Windows/macOS, and in‑app preview usage.

### Fixed
- AI analysis UI would appear idle after reaching OpenAI; added timeouts and explicit completion messaging with output locations.
- PDF preview reliability: fallback to `pdf2image` + Poppler if PyMuPDF rendering fails, with clear error reporting.

### Dependency Notes
- Pinned `httpx==0.27.2` for compatibility with `openai==1.23.2`.

---
## [1.1.0] - 2025-08-28
### Added
- PyQt app: per-file progress updates and a new progress label beneath the spinner on Bank Statement Analyzer (`bank_progress` signal + label).
- PyQt app: OCR-first toggle on Bank Statement Analyzer; sets `BANK_OCR_FIRST=1` for the worker run.
- Bank analyzer: environment-driven OCR flow (`BANK_OCR_FIRST`), with Tesseract configuration via `BANK_OCR_CONFIG` (defaults to `--psm 6`).
- Bank analyzer: robust header detection helper (`_matches_header_text`) and `detect_section_headers()` for diagnostics.
- Bank analyzer: writes diagnostic files per statement:
  - "Headers Debug.txt" (detected deposit/withdrawal/other header-like lines)
  - "Deposit Lines Debug.txt" (lines actually counted with amounts)
- Bank analyzer: Berkshire Bank profile (`detect_berkshire_bank`, `_summarize_processors_berkshire`).
- Bank analyzer: U.S. Bank profile (`detect_us_bank`, `_summarize_processors_us_bank`).

### Changed
- PyQt app: all long-running tasks now update the UI via Qt signals; spinners and message boxes are driven on the main thread.
- PyQt app: PIL→QPixmap conversion uses in-memory `ImageQt` (no temp files; avoids non-existent `toqimage`).
- PyQt app: bank analyzer drag-and-drop filters to `.pdf` only and warns on invalid drops.
- Bank analyzer: summarization prefers the leftmost positive amount per transaction line (credit column), ignores negatives/parentheses and running balances.
- Bank analyzer: section-aware logic tightened; deposit/withdrawal headers expanded (Deposits/Credits, Credits(+), Direct/Mobile/Check/Cash Deposit, etc.).
- Bank analyzer: header fuzzy matching limited to short lines to avoid false positives from long notices/banners; word-boundary matching for short tokens.
- Bank analyzer: page-level processor detection filters to deposit-context lines using headers + keyword heuristics.

### Fixed
- PyQt app: edit dialog saved fields in wrong order and with an extra argument; now calls `edit_merchant_by_id` with the correct parameter order.
- PyQt app: stylesheets had extra closing braces causing f-string errors; corrected.
- PyQt app: worker threads previously called `QMessageBox` directly; now use signals to avoid thread-safety issues.
- bsa_settings: `approve_suggestions` now uses `add_merchant_full("", name)` (correct argument mapping) and removes noisy import debug prints.
- Bank analyzer: Python <3.10 compatibility by using `Optional[str]` instead of `str | None` in annotations.


---
## [1.0.0] - 2025-08-20
### Removed
- **main_app_pyqt.py**
  - Removed the file and will create a new branch with UI on new release
  - Remove Bloat from binaries .. not needed in Repo
### Fixed
- **ai_analysis.py**
  - Removed conditional redefinitions and all `type: ignore` comments that caused mypy noise.
  - Added a version-tolerant OpenAI chat wrapper (works with both new `OpenAI` client and legacy `ChatCompletion`).
  - Fixed a stray f-string brace in the summary filename.
  - Trailing Whitespace
- **bank_analyzer.py**
  - Renamed ambiguous variable `l` to `line_lower` (ruff E741).
  - Removed a duplicate `extract_text_from_pdf` definition (ruff F811).
  - Trailing Whitespace
  - Changed `openai_api_key = config.openai_api_key` to `openai.api_key = os.getenv("OPENAI_API_KEY")` line 524
- **utils/pdf_utils.py**
  - Reworked `compress_pdf` to be PyMuPDF-version-safe and reliable: now rasterizes each page to JPEG at a controlled DPI and quality (consistent size reduction across versions).

### Added
- **Tests**
  - `tests/test_pdf_compress_large.py`: creates a large image PDF and asserts ≥20% size reduction after compression.
  - `tests/test_ai_analysis_parse.py`: smoke tests for parsing/summing helpers in `ai_analysis`.
  - `tests/conftest.py`: ensures the project root is on `sys.path` for imports during tests.
  - `tests/cli.py`: makes sure the pdf utils cli does not fail
  - `tests/test_pdf_compress.py`: Smoke test: ensures function runs and reduces or keeps size reasonable.

### Changed
- **Compression behavior**
  - `compress_pdf` keeps the same signature but now rasterizes pages for predictable results.
    _Note_: Rasterization makes text non-selectable (appropriate for scanned statements). If vector/text preservation is needed later, we can add an alternate non-raster path behind a flag.

### Tooling
- **pre-commit / mypy**
  - mypy hook uses `pass_filenames: false` with explicit targets to avoid duplicate-module scans.
- **pyproject**
  - Moved Ruff config to `[tool.ruff.lint]`, kept rules focused (`E`, `F`, `I`) while stabilizing.
  - mypy set to Python 3.11 with sensible excludes (local venvs, caches).

### Docs
- Recommend targeting **Python 3.11** so PyMuPDF installs from wheels (no native build).

## [1.0.0] - 2025-08-19
### Added
- Initial release of the tools and baseline analysis workflow.

[Unreleased]: https://github.com/aptech3/ap3te
