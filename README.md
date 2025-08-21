# RSG Recovery Tools

**RSG Recovery Tools** is a collection of utilities for processing and analyzing bank statements and related documents.
It uses [Tesseract OCR](https://github.com/tesseract-ocr/tesseract) (via `pytesseract`) and PDF parsing libraries (`PyPDF2`, `fitz`, etc.) to extract, summarize, and clean data for downstream use.

---

## Features
- Extract text from PDFs (including scanned documents) using OCR
- Summarize and normalize bank statements
- Tools for compressing and cleaning large PDFs
- Extensible: add custom rules for your agency or client workflows
- Cross-platform (Linux, macOS, Windows)

---

## Requirements
- **Python** 3.9+
- **Tesseract OCR** (must be installed separately, see below)
- (Optional) **Poppler** if using advanced PDF features

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

Clone the repo and install Python dependencies:

```bash
git clone https://github.com/AmberRSG/rsg-recovery-tools.git
cd rsg-recovery-tools
pip install -r requirements.txt
```

(Optional) If using a virtual environment:

```bash
python -m venv .venv
source .venv/bin/activate  # Linux/macOS
.venv\Scripts\activate     # Windows
pip install -r requirements.txt
```

---

## Usage

### Running the App
If your main entry point is `main_app.py`:

```bash
python main_app.py
```

The app will launch a Tkinter-based GUI where you can load and process bank statement PDFs.

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

GitHub Actions run tests on pushes to `pre-prod` and `main`.

Example pipeline includes:
- Installing Tesseract on CI runners
- Running unit tests
- Packaging for release (future work)

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
