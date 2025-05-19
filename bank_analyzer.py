import sys
import os
import re
from pathlib import Path
import PyPDF2
import fitz  # PyMuPDF for robust PDF reading & redaction
from thefuzz import fuzz
import bsa_settings  # Your DB logic!
import openai
from reportlab.lib.pagesizes import letter
from reportlab.pdfgen import canvas
import config  # <-- Make sure you have openai_api_key in config.py
from pdf2image import convert_from_path
import pytesseract
import shutil
from reportlab.lib.pagesizes import letter
from reportlab.pdfgen import canvas

def get_tesseract_cmd():
    """
    Return a working tesseract command:
      1) bundled copy if running a PyInstaller bundle,
      2) installed location if on dev machine,
      3) fallback to system PATH.
    """
    # 1) Bundled with PyInstaller?
    base = getattr(sys, "_MEIPASS", os.path.abspath(os.path.dirname(__file__)))
    bundled = os.path.join(base, "tesseract", "tesseract.exe")
    if os.path.isfile(bundled):
        return bundled

    # 2) Common dev install location
    dev_path = r"C:\Program Files\Tesseract-OCR\tesseract.exe"
    if os.path.isfile(dev_path):
        return dev_path

    # 3) Fallback: rely on PATH
    if shutil.which("tesseract"):
        return "tesseract"

    # If we get here, nothing was found
    raise FileNotFoundError(
        "Tesseract executable not found. "
        "Please install it or add it to your PATH."
    )

# Then:
pytesseract.pytesseract.tesseract_cmd = get_tesseract_cmd()


# ===== Output Directory Helpers =====

def get_poppler_path():
    """
    Returns the folder containing Poppler executables (pdftoppm.exe, pdfinfo.exe).
    Checks both poppler/bin and poppler/Library/bin under the base directory.
    """
    base = getattr(sys, "_MEIPASS", os.path.abspath(os.path.dirname(__file__)))
    poppler_root = os.path.join(base, "poppler")
    # possible locations
    candidates = [
        os.path.join(poppler_root, "bin"),
        os.path.join(poppler_root, "Library", "bin"),
    ]
    for p in candidates:
        if os.path.isdir(p):
            return p
    raise FileNotFoundError(f"No Poppler bin folder found in {poppler_root}")

def get_desktop_output_folder():
    """Returns the standard output folder path on the user's desktop, creating it if necessary."""
    desktop = Path.home() / "Desktop"
    output = desktop / "RSG Recovery Tools data output"
    output.mkdir(parents=True, exist_ok=True)
    return output

def get_statement_subfolder(pdf_path):
    """
    Returns the output subfolder path for this statement, creating it if necessary.
    Strips common suffixes for naming.
    """
    company_name = extract_company_name(pdf_path)
    main_output = get_desktop_output_folder()
    subfolder = main_output / company_name
    subfolder.mkdir(parents=True, exist_ok=True)
    return subfolder

def extract_company_name(pdf_path):
    """
    Extracts the base file name minus 'bank statements' or similar suffixes.
    """
    base = os.path.basename(pdf_path)
    name = os.path.splitext(base)[0]
    # Remove common suffixes, customizable as needed
    for suffix in [" Bank Statements", " bank statements", " statement", " Statement"]:
        if name.endswith(suffix):
            name = name[:-len(suffix)]
    return name.strip()


# ===== Redaction Logic =====

def redact_pdf_page(input_pdf_path, page_num, output_pdf_path, keyword=None):
    """
    Redacts account/routing numbers and highlights merchant name if provided.
    """
    doc = fitz.open(input_pdf_path)
    page = doc[page_num]
    if keyword:
        rects = page.search_for(keyword)
        for rect in rects:
            page.add_highlight_annot(rect)
    text = page.get_text()
    for match in re.finditer(r'(?<!\d)(\d{9,12})(?!\d)', text):
        redaction_rects = page.search_for(match.group())
        for rect in redaction_rects:
            page.add_redact_annot(rect, fill=(1, 1, 1))
    page.apply_redactions()
    single_page_doc = fitz.open()
    single_page_doc.insert_pdf(doc, from_page=page_num, to_page=page_num)
    single_page_doc.save(output_pdf_path)
    single_page_doc.close()
    doc.close()


# ===== Merchant Processor Page Matching =====

def find_processor_pages(pdf_path, merchant_keywords, fuzzy_threshold=80, add_suggestions=True):
    """
    Returns a dict {processor_name: [page_num, ...]} where merchant processor is matched
    AND the transaction is a deposit/credit/income.
    """
    processor_pages = {}
    suggestions = set()
    try:
        reader = PyPDF2.PdfReader(pdf_path)
        for i, page in enumerate(reader.pages):
            text = page.extract_text() or ''
            text_lines = text.splitlines()
            for line in text_lines:
                line_lower = line.lower()
                # "deposit", "credit", or similar signals INCOME (expand as needed)
                is_deposit = any(w in line_lower for w in [
                    "deposit", "credit", "received from", "payment from", "inc/", "payment received"
                ])
                for keyword in merchant_keywords:
                    keyword_lower = keyword.lower()
                    # Must match merchant AND be a deposit line
                    if (keyword_lower in line_lower or fuzz.partial_ratio(keyword_lower, line_lower) >= fuzzy_threshold) and is_deposit:
                        if i not in processor_pages.get(keyword, []):
                            processor_pages.setdefault(keyword, []).append(i)
                # --- Suggest logic, only for deposit lines
                if is_deposit:
                    match = re.search(r"(deposit|credit|payment from|received from)\s*([A-Za-z0-9\-\.\&\s]+)", line, re.IGNORECASE)
                    if match:
                        possible_merchant = match.group(2).strip()
                        if possible_merchant and len(possible_merchant) > 2:
                            suggestions.add((possible_merchant, os.path.basename(pdf_path)))
        if add_suggestions:
            for name, found_in_file in suggestions:
                bsa_settings.add_suggestion(name, found_in_file)
    except Exception as e:
        print(f"Error reading {pdf_path}: {e}")
    return processor_pages


# ===== Save Redacted Pages per Processor =====

def save_processor_pages(pdf_path, processor_matches, subfolder):
    """
    Saves redacted copies of matching pages for each processor found into the subfolder.
    If a processor has more than one page, add a count.
    """
    company_name = extract_company_name(pdf_path)
    for processor, pages in processor_matches.items():
        safe_processor = re.sub(r'[\\/:"*?<>|]+', "_", processor)
        for idx, page_num in enumerate(pages, 1):
            # If more than one page for this processor, add (2), (3), etc.
            extra = f" ({idx})" if len(pages) > 1 else ""
            filename = f"{company_name} {safe_processor}{extra}.pdf"
            output_path = subfolder / filename
            redact_pdf_page(pdf_path, page_num, str(output_path), keyword=processor)



# ===== GPT Summary Analysis and PDF Generation =====
def extract_text_from_pdf(pdf_path):
    import pdfplumber, pytesseract

    # 1) Try text-based extraction
    with pdfplumber.open(pdf_path) as pdf:
        text = "\n".join(page.extract_text() or "" for page in pdf.pages)
    if text.strip():
        return text

    # 2) OCR fallback
    poppler_path = get_poppler_path()
    images = convert_from_path(pdf_path, poppler_path=poppler_path)
    ocr_text = ""
    for img in images:
        ocr_text += pytesseract.image_to_string(img) + "\n"
    return ocr_text


def gpt_analyze_bank_statement(pdf_path, openai_api_key, subfolder):
    company_name = extract_company_name(pdf_path)
    all_text = extract_text_from_pdf(pdf_path)  # Robust text extraction!

    prompt = f"""
You are a collections specialist. Analyze the following bank statement and produce your output in this exact format.
Do not use Markdown or tables.

---FORMAT START---

Income Sources Analysis
- List every deposit source (cash, check, wire, and each merchant processor such as Square, Stripe, Fiserv, Intuit, etc).
- For each, print only the total dollar amount received from that source, like:
  • Square: $XXXX.XX
  • Fiserv: $XXXX.XX
  • Stripe: $XXXX.XX

Percentage of Income from Each Source
- For each deposit source above, show the percent of total income it represents (example: Square: $X / $TOTAL = X%).

Linked Accounts (Last 4 Digits)
- List every unique last 4 digits of account numbers that show up in any "transfer to" or "transfer from" or "ACH" transaction.
- For each, include the last 4, direction (in/out), and the company/bank name if available.
- If none are found, write "None found."

Potential Other MCA Activity
- Review all withdrawals and deposits.
- List any transactions where the other party's name includes "funding," "funder," or "capital" (case-insensitive, skip those with "factor" or "factoring").
- For each, specify direction (payment to/deposit from), name, and amount.
- If none are found, write "None found."

Main Spending Patterns
- List major categories of spending as bullets.

Questionable or Non-Business Expenses
- For each type, show the count of transactions, total spent, and percent of income (example: Uber Eats: 4 transactions, $120.00, 2.5%).

Evidence of Commingling of Business/Personal Funds
- For each, show count, total, and percent of income.

Other Collector-Relevant Insights
- Any other information that would be helpful to a collections professional.

---FORMAT END---

STATEMENT TEXT:
{all_text}
"""
    openai.api_key = openai_api_key
    response = openai.chat.completions.create(
        model="gpt-4-turbo",
        messages=[{"role": "user", "content": prompt}],
        max_tokens=2048,
        temperature=0.1,
    )
    summary = response.choices[0].message.content.strip()
    summary = clean_for_pdf(summary)  # <--- REMOVE ASTERISKS AND FORMATTING!

    # PDF creation with wrapping
    summary_filename = f"{company_name} Summary.pdf"
    summary_path = subfolder / summary_filename
    c = canvas.Canvas(str(summary_path), pagesize=letter)
    width, height = letter
    margin = 40
    y = height - margin

    c.setFont("Helvetica-Bold", 16)
    c.drawString(margin, y, f"{company_name} - Bank Statement Summary")
    y -= 28
    c.setFont("Helvetica", 11)

    section_titles = [
    "Income Sources Analysis",
    "Percentage of Income from Each Source",
    "Linked Accounts (Last 4 Digits)",
    "Potential Other MCA Activity",
    "Main Spending Patterns",
    "Questionable or Non-Business Expenses",
    "Evidence of Commingling of Business/Personal Funds",
    "Other Collector-Relevant Insights"
]

    for line in summary.split('\n'):
        line = line.strip()
        if not line:
            y -= 10
            continue
        # Check if line matches a section header (case-insensitive, strip punctuation)
        if any(line.lower().startswith(title.lower()) for title in section_titles):
            c.setFont("Helvetica-Bold", 12)
            for wrapline in wrap_text(line, width=90):
                c.drawString(margin, y, wrapline)
                y -= 16
            c.setFont("Helvetica", 11)
        elif line.startswith("• ") or line.startswith("- "):
            text = line[2:]
            bullet = "• "
            for i, wrapline in enumerate(wrap_text(text, width=85)):
                c.drawString(margin + 18, y, (bullet if i == 0 else "  ") + wrapline)
                y -= 13
        else:
            for wrapline in wrap_text(line, width=90):
                c.drawString(margin, y, wrapline)
                y -= 13
        if y < margin + 24:
            c.showPage()
            y = height - margin
            c.setFont("Helvetica", 11)
    c.save()
    return str(summary_path)


def clean_for_pdf(text):
    """
    Remove Markdown-style bold/italics from GPT output.
    - Removes **, __, `, etc.
    """
    # Remove **bold** and __underline__ and backticks
    text = re.sub(r'\*\*([^\*]+)\*\*', r'\1', text)
    text = re.sub(r'__([^_]+)__', r'\1', text)
    text = text.replace('`', '')
    return text

def wrap_text(text, width=90):
    import textwrap
    return textwrap.wrap(text, width=width)

# ===== Main Entry Point for Processing =====

def process_bank_statements_full(filepaths, openai_api_key, content_frame=None):
    """
    Full pipeline: match processors, save redacted pages, run GPT summary.
    Optionally updates a Tkinter content_frame.
    """
    merchant_keywords = bsa_settings.get_all_merchants()

    for pdf_path in filepaths:
        subfolder = get_statement_subfolder(pdf_path)
        processor_matches = find_processor_pages(pdf_path, merchant_keywords)
        save_processor_pages(pdf_path, processor_matches, subfolder)
        summary_path = gpt_analyze_bank_statement(pdf_path, openai_api_key, subfolder)

        # If using Tkinter content frame for UI updates, show results
        if content_frame is not None:
            from customtkinter import CTkLabel
            for widget in content_frame.winfo_children():
                widget.destroy()
            CTkLabel(content_frame, text="Analysis Complete!", font=("Arial", 22, "bold"), text_color="#0075c6").pack(pady=(25, 10))
            CTkLabel(content_frame, text=f"Redacted processor pages and summary PDF saved to:\n{subfolder}", font=("Arial", 12), text_color="#333").pack(pady=(10, 2))
            CTkLabel(content_frame, text=f"Latest summary: {os.path.basename(summary_path)}", font=("Arial", 12), text_color="#555").pack(anchor="w", padx=30)


# ===== Minimal CLI Usage =====

if __name__ == "__main__":
    import sys
    openai_api_key = config.openai_api_key
    files = sys.argv[1:]
    if not files:
        print("Usage: python bank_analyzer.py file1.pdf [file2.pdf ...]")
        sys.exit(1)
    process_bank_statements_full(files, openai_api_key)
