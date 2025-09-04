# RSG Recovery Tools

**RSG Recovery Tools** is a PyQt desktop application and toolkit for processing and analyzing bank statements and related documents. It combines robust PDF parsing with optional OCR and an AI‑powered statement analysis workflow (OpenAI).

---

## Features
- AI Statement Analysis: GPT‑based extraction and summary, outputs a concise PDF and now previews the summary inside the app (zoom + page navigation).
- Bank Statement Analyzer: detect processors, totals, and linked accounts with optional OCR and diagnostics.
- EVG Recovery Splitter: split EVG Recovery PDFs; auto‑redact Mulligan contracts when detected.
- BSA Settings: manage merchant processor and exclusion lists.
- PDF utilities: redaction helpers, compression, and extraction utilities.
- Cross‑platform: Windows 11 and macOS supported. Linux works from source.

---

## Requirements
- For packaged builds (recommended for agents): none — just run the downloaded binary.
- For running from source:
  - **Python** 3.11 recommended (wheels available for PyMuPDF)
  - **Tesseract OCR** (optional; used for OCR when needed)
  - **Poppler** (optional; used by `pdf2image` fallback in previews)
  - **OpenAI API key** for AI analysis (`OPENAI_API_KEY`)

### Install Tesseract
- **Windows**:
  ```powershell
  choco install tesseract
  ```
- **macOS**:
  ```bash
  brew install tesseract
  ```
- **Linux (Debian/Ubuntu)**:
  ```bash
  sudo apt-get update && sudo apt-get install -y tesseract-ocr tesseract-ocr-eng
  ```

---

## Installation

### Windows 11 (agents)
- Download `RSG-Recovery-Tools.exe` from GitHub Actions artifacts (workflow: `Build Desktop Apps`) or from Releases if published.
- Double‑click to run. No installer or Python required.

### macOS (agents)
- Download the `RSG-Recovery-Tools` app binary from GitHub Actions artifacts.
- First launch: right‑click → Open (Gatekeeper). For a smoother UX, code signing/notarization can be added.

### From source (devs)
```bash
git clone https://github.com/AmberRSG/rsg-recovery-tools.git
cd rsg-recovery-tools
python -m venv .venv
source .venv/bin/activate  # macOS/Linux
# .venv\Scripts\activate   # Windows
pip install -r requirements.txt
```

---

## Usage

### Running the App
Run the PyQt app:
```bash
python main_app_pyqt.py
```
The app launches with pages for Bank Analyzer, AI Statement Analysis, EVG Splitter, and BSA Settings.

### Command-line Utilities
Some scripts can be run directly, for example:

```bash
python bank_analyzer.py input.pdf
```

---

## Testing

We use [pytest](https://docs.pytest.org/) for unit and smoke tests.

Run the test suite:

```bash
pytest -q
```

Tests include:
- OCR availability (checks if `tesseract` is installed)
- PDF compression works correctly
- Bank statement summarization logic

---

## Development Workflow

We use a **branching model** for safety:
- `main`: production-ready code
- `pre-prod`: staging branch for integration and testing
- `feature/*` or `fix/*`: short-lived branches for specific issues

Typical flow:
```
feature/bugfix → pre-prod → main
```

Pull requests should target `pre-prod`. Once validated, code is merged into `main`.

---

## CI/CD

- GitHub Actions build workflow: `.github/workflows/build.yml`
  - Builds single‑file artifacts for Windows (`.exe`) and macOS (binary) using PyInstaller.
  - Uploads build artifacts for download.
  - Uses `requirements-build.txt` for a stable build environment.

---

## Contributing

1. Fork the repo
2. Create a branch:
   ```bash
   git checkout -b feature/your-feature
   ```
3. Commit your changes:
   ```bash
   git commit -m "feat: add new feature"
   ```
4. Push to your branch:
   ```bash
   git push origin feature/your-feature
   ```
5. Submit a Pull Request

---

## License
This project is licensed under the MIT License.
See the [LICENSE](LICENSE) file for details.

---

## Notes
- Do **not** commit `tesseract/`, `poppler/`, or other binary blobs to source control.
- Instead, list dependencies in `requirements.txt` and rely on package managers (`apt`, `brew`, `choco`) for installing binaries.
- If you need trained OCR models (`.traineddata`), commit them via [Git LFS](https://git-lfs.com/).
 - For AI analysis, set `OPENAI_API_KEY` in your environment or via the app’s “Set/OpenAI Key” dialog.
