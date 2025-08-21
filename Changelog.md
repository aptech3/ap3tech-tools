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
