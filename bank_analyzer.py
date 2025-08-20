import os
import re
import shutil
import sys
from pathlib import Path

import fitz  # PyMuPDF for robust PDF reading & redaction
import PyPDF2
import pytesseract
from pdf2image import convert_from_path
from reportlab.lib.pagesizes import letter
from reportlab.pdfgen import canvas
from thefuzz import fuzz

import bsa_settings  # Your DB logic!


def get_tesseract_cmd():
    base = getattr(sys, "_MEIPASS", os.path.abspath(os.path.dirname(__file__)))
    bundled = os.path.join(base, "tesseract", "tesseract.exe")
    if os.path.isfile(bundled):
        return bundled
    dev_path = r"C:\Program Files\Tesseract-OCR\tesseract.exe"
    if os.path.isfile(dev_path):
        return dev_path
    if shutil.which("tesseract"):
        return "tesseract"
    raise FileNotFoundError(
        "Tesseract executable not found. Please install it or add it to your PATH."
    )


pytesseract.pytesseract.tesseract_cmd = get_tesseract_cmd()


def get_poppler_path():
    base = getattr(sys, "_MEIPASS", os.path.abspath(os.path.dirname(__file__)))
    poppler_root = os.path.join(base, "poppler")
    candidates = [
        os.path.join(poppler_root, "bin"),
        os.path.join(poppler_root, "Library", "bin"),
    ]
    for p in candidates:
        if os.path.isdir(p):
            return p
    raise FileNotFoundError(f"No Poppler bin folder found in {poppler_root}")


def get_desktop_output_folder():
    desktop = Path.home() / "Desktop"
    output = desktop / "RSG Recovery Tools data output"
    output.mkdir(parents=True, exist_ok=True)
    return output


def get_statement_subfolder(pdf_path):
    company_name = extract_company_name(pdf_path)
    main_output = get_desktop_output_folder()
    subfolder = main_output / company_name
    subfolder.mkdir(parents=True, exist_ok=True)
    return subfolder


def extract_company_name(pdf_path):
    base = os.path.basename(pdf_path)
    name = os.path.splitext(base)[0]
    for suffix in [" Bank Statements", " bank statements", " statement", " Statement"]:
        if name.endswith(suffix):
            name = name[: -len(suffix)]
    return name.strip()


def is_excluded(processor, exclusion_keywords, threshold=85):
    processor = processor.lower().strip()
    for exclusion in exclusion_keywords:
        if fuzz.ratio(processor, exclusion.lower().strip()) >= threshold:
            return True
    return False


def redact_pdf_page(input_pdf_path, page_num, output_pdf_path, keyword=None):
    doc = fitz.open(input_pdf_path)
    page = doc[page_num]
    if keyword:
        if keyword == "Stripe":
            st_pattern = re.compile(r"St-[A-Za-z0-9]{12}")
            for match in st_pattern.findall(page.get_text()):
                rects = page.search_for(match)
                for rect in rects:
                    page.add_highlight_annot(rect)
        elif keyword == "Square":
            for sqvar in ["Square", "SQ*", "SQ *", "SQUAREUP", "SQ"]:
                rects = page.search_for(sqvar)
                for rect in rects:
                    page.add_highlight_annot(rect)
        else:
            rects = page.search_for(keyword)
            for rect in rects:
                page.add_highlight_annot(rect)
    text = page.get_text()
    for match in re.finditer(r"(?<!\d)(\d{9,12})(?!\d)", text):
        redaction_rects = page.search_for(match.group())
        for rect in redaction_rects:
            page.add_redact_annot(rect, fill=(1, 1, 1))
    page.apply_redactions()
    single_page_doc = fitz.open()
    single_page_doc.insert_pdf(doc, from_page=page_num, to_page=page_num)
    single_page_doc.save(output_pdf_path)
    single_page_doc.close()
    doc.close()


def extract_possible_processor_name(line):
    # Remove date, transaction descriptors, extra junk
    line = re.sub(r"^\d{1,2}[/\-]\d{1,2}[/\-]\d{2,4}", "", line).strip()
    line = re.sub(
        r"(POS|PURCHASE|NON\-PIN|ACH|TRANSFER|PMT|DEPOSIT|WITHDRAWAL|ATM|DIRECT DEP|INTEREST|CHECK|BALANCE|PAYROLL|PRIDE BASICS|SBFS|LIMIT|INTERNAL|VENDOR|MOBILE|FEE)",
        "",
        line,
        flags=re.IGNORECASE,
    )
    # Try to match company name, strip after first location/city/state
    company_match = re.search(r"([A-Z][A-Z\s&\-\*]{2,})(?:[\s,]+[A-Z]{2,}|$)", line)
    if company_match:
        # Uber Eats, SPECTRUM, WALMART etc.
        name = company_match.group(1).strip()
        # Remove city, state, numbers, trailing junk
        name = re.sub(r"\s+[A-Z]{2,}.*$", "", name)  # Cut after city/state code
        name = re.sub(r"\d+", "", name)  # Remove numbers
        return name.strip()
    # Fallback: up to 2 capitalized words in a row
    capwords = re.findall(r"\b([A-Z][a-zA-Z]+)\b", line)
    if capwords:
        return " ".join(capwords[:2])
    return " ".join(line.split()[:2]).strip()


def find_processor_pages(pdf_path, merchant_keywords, debtor_name):
    processor_pages = {}
    seen_normalized = set()
    SKIP_WORDS = [
        "payroll",
        "ytd",
        "overdraft",
        "interest",
        "tax",
        "wire",
        "atm",
        "available",
        "accrued",
        "ads",
        "transfer",
    ]
    try:
        reader = PyPDF2.PdfReader(pdf_path)
        for i, page in enumerate(reader.pages):
            text = page.extract_text() or ""
            for line in text.splitlines():
                line_lower = line.lower()

                # Only look at deposit/credit lines (no negatives, no "withdrawal" words)
                amounts = re.findall(r"\$?(-?[\d,]+\.\d\d)", line)
                is_deposit = any(
                    not amt.replace(",", "").strip().startswith("-") for amt in amounts
                )
                if not is_deposit:
                    continue

                # KNOWN merchant processors
                for keyword in merchant_keywords:
                    keyword_lower = keyword.lower()
                    if keyword_lower in line_lower and keyword_lower not in seen_normalized:
                        processor_pages[keyword] = i
                        seen_normalized.add(keyword_lower)
                        break

                # POSSIBLE processor
                if debtor_name.lower() not in line_lower and not any(
                    k.lower() in line_lower for k in merchant_keywords
                ):
                    possible_name = extract_possible_processor_name(line)
                    norm = possible_name.lower().strip()
                    if (
                        possible_name
                        and len(possible_name) > 2
                        and norm not in seen_normalized
                        and re.search(r"[a-zA-Z]", possible_name)
                        and not any(skip in norm for skip in SKIP_WORDS)
                    ):
                        processor_pages[f"Possible Processor - {possible_name}"] = i
                        seen_normalized.add(norm)
    except Exception as e:
        print(f"Error reading {pdf_path}: {e}")
    return processor_pages


def find_processor_pages_with_exclusion(
    pdf_path, merchant_keywords, debtor_name, exclusion_keywords
):
    processor_pages = {}
    seen_normalized = set()
    SKIP_WORDS = [
        "payroll",
        "ytd",
        "overdraft",
        "interest",
        "tax",
        "wire",
        "atm",
        "available",
        "accrued",
        "ads",
        "transfer",
    ]
    try:
        reader = PyPDF2.PdfReader(pdf_path)
        for i, page in enumerate(reader.pages):
            text = page.extract_text() or ""
            for line in text.splitlines():
                line_lower = line.lower()

                # Only look at deposit/credit lines (no negatives, no "withdrawal" words)
                amounts = re.findall(r"\$?(-?[\d,]+\.\d\d)", line)
                is_deposit = any(
                    not amt.replace(",", "").strip().startswith("-") for amt in amounts
                )
                if not is_deposit:
                    continue

                # KNOWN merchant processors
                for keyword in merchant_keywords:
                    keyword_lower = keyword.lower()
                    # Exclusion check for known keywords
                    if keyword_lower in line_lower and keyword_lower not in seen_normalized:
                        # Fuzzy check against exclusions
                        if is_excluded(keyword_lower, exclusion_keywords):
                            continue
                        processor_pages[keyword] = i
                        seen_normalized.add(keyword_lower)
                        break

                # POSSIBLE processor
                if debtor_name.lower() not in line_lower and not any(
                    k.lower() in line_lower for k in merchant_keywords
                ):
                    possible_name = extract_possible_processor_name(line)
                    norm = possible_name.lower().strip()
                    if (
                        possible_name
                        and len(possible_name) > 2
                        and norm not in seen_normalized
                        and re.search(r"[a-zA-Z]", possible_name)
                        and not any(skip in norm for skip in SKIP_WORDS)
                    ):
                        if is_excluded(possible_name, exclusion_keywords):
                            continue
                        processor_pages[f"Possible Processor - {possible_name}"] = i
                        seen_normalized.add(norm)
    except Exception as e:
        print(f"Error reading {pdf_path}: {e}")
    return processor_pages


def save_processor_pages(pdf_path, processor_matches, subfolder):
    company_name = extract_company_name(pdf_path)
    for processor, page_num in processor_matches.items():
        safe_processor = re.sub(r'[\\/:"*?<>|]+', "_", processor)
        filename = f"{company_name} {safe_processor} p{page_num+1}.pdf"
        output_path = subfolder / filename

        doc = fitz.open(pdf_path)
        page = doc[page_num]
        text = page.get_text()
        rects_to_highlight = []

        # Use the base name for highlighting (for Possible Processor and known processors)
        if processor.startswith("Possible Processor - "):
            highlight_term = processor.replace("Possible Processor - ", "")
        else:
            highlight_term = processor

        # Case-insensitive search (PyMuPDF's default)
        matches = page.search_for(highlight_term)
        rects_to_highlight.extend(matches)

        # If no matches found, try the first word only (case-insensitive)
        if not rects_to_highlight:
            main_word = highlight_term.split()[0]
            matches = page.search_for(main_word)
            rects_to_highlight.extend(matches)

        # Highlight all matched rectangles
        for rect in rects_to_highlight:
            page.add_highlight_annot(rect)

        # Redact account numbers (leave last 4)
        for match in re.finditer(r"(?<!\d)(\d{9,12})(?!\d)", text):
            redaction_rects = page.search_for(match.group())
            for rect in redaction_rects:
                page.add_redact_annot(rect, fill=(1, 1, 1))

        page.apply_redactions()

        # Save single-page PDF
        single_page_doc = fitz.open()
        single_page_doc.insert_pdf(doc, from_page=page_num, to_page=page_num)
        single_page_doc.save(output_path)
        single_page_doc.close()
        doc.close()


def extract_text_from_pdf(pdf_path):
    import pdfplumber
    import pytesseract

    with pdfplumber.open(pdf_path) as pdf:
        text = "\n".join(page.extract_text() or "" for page in pdf.pages)
    if text.strip():
        return text
    poppler_path = get_poppler_path()
    images = convert_from_path(pdf_path, poppler_path=poppler_path)
    ocr_text = ""
    for img in images:
        ocr_text += pytesseract.image_to_string(img) + "\n"
    return ocr_text


def process_bank_statements_full(filepaths, content_frame=None):
    # Get merchant processors (known) and exclusions
    merchant_keywords = bsa_settings.get_all_merchants() + [
        "Square",
        "Stripe",
        "Intuit",
        "Coinbase",
        "Etsy",
        "PayPal",
    ]
    exclusion_keywords = [e[1] for e in bsa_settings.get_all_exclusions_with_ids()]

    def is_excluded(processor):
        # Local version, can use the global if preferred
        processor = processor.lower().strip()
        for exclusion in exclusion_keywords:
            if fuzz.ratio(processor, exclusion.lower().strip()) >= 85:
                return True
        return False

    for pdf_path in filepaths:
        subfolder = get_statement_subfolder(pdf_path)
        debtor_name = extract_company_name(pdf_path)

        # Save highlighted/redacted processor pages (merchant and unknown non-debtor names)
        processor_matches = {}

        # Updated processor page finding logic (incorporating exclusion filtering)
        all_matches = find_processor_pages_with_exclusion(
            pdf_path, merchant_keywords, debtor_name, exclusion_keywords
        )

        # Save only non-excluded pages
        for processor, page_num in all_matches.items():
            processor_clean = processor.replace("Possible Processor - ", "").lower().strip()
            if is_excluded(processor_clean):
                continue
            processor_matches[processor] = page_num

        save_processor_pages(pdf_path, processor_matches, subfolder)

        # --- BASIC SUMMARY SECTION ---
        text = extract_text_from_pdf(pdf_path)

        # Merchant processor summary: one line per processor, total and %
        # (Optionally skip exclusions here too, for extra thoroughness)
        filtered_processors = [proc for proc in merchant_keywords if not is_excluded(proc)]
        processor_totals, total_income = summarize_processors(text, filtered_processors)

        # Linked accounts: only ones mentioned on transfer/ACH-type lines
        linked_accounts = summarize_linked_accounts(text)

        # Possible MCAs
        possible_mcas = find_possible_mcas(text)

        summary_pdf = subfolder / f"{debtor_name} Summary.pdf"
        write_basic_summary_pdf(
            debtor_name, summary_pdf, processor_totals, total_income, linked_accounts, possible_mcas
        )


def summarize_linked_accounts(text):
    # Look for lines indicating transfers (ACH, XFER, etc.) and extract last 4s
    transfer_keywords = [
        "transfer",
        "xfer",
        "ach",
        "external account",
        "to acct",
        "from acct",
        "withdrawal",
        "deposit",
    ]
    lines = text.splitlines()
    accounts = set()
    for line in lines:
        line_lower = line.lower()
        if any(k in line_lower for k in transfer_keywords):
            # Look for last 4 digit account patterns
            # Look for last 4 digit account patterns
            for m in re.findall(r"\b(\d{4})\b", line):
                accounts.add(m)
    return sorted(accounts)


def summarize_processors(text, known_processors):
    processor_totals = {}
    total_income = 0

    lines = text.splitlines()
    for proc in known_processors:
        proc_total = 0.0
        proc_regex = re.compile(rf"{re.escape(proc)}", re.IGNORECASE)
        for line in lines:
            if proc_regex.search(line):
                # Look for *any* $ amount on this line
                amounts = re.findall(r"\$?([\d,]+\.\d\d)", line)
                for amt in amounts:
                    try:
                        proc_total += float(amt.replace(",", ""))
                    except ValueError:
                        continue
        if proc_total > 0:
            processor_totals[proc] = round(proc_total, 2)
            total_income += proc_total
    return processor_totals, total_income


def find_possible_mcas(text):
    # Keywords you want to flag
    mca_keywords = ["fund", "funder", "funding", "capital", "advance"]
    lines = text.splitlines()
    results = []
    for line in lines:
        lower = line.lower()
        if any(word in lower for word in mca_keywords):
            results.append(line.strip())
    return results


def write_linked_accounts_summary(c, margin, y, linked_accounts):
    if not linked_accounts:
        c.drawString(margin, y, "None found.")
        y -= 16
    else:
        for acct in linked_accounts:
            c.drawString(margin, y, f"Account: {acct}")
            y -= 16
    return y


def write_processor_summary(c, margin, y, processor_totals, total_income):
    if not processor_totals:
        c.drawString(margin, y, "None found.")
        y -= 16
    else:
        for proc, total in sorted(processor_totals.items(), key=lambda x: -x[1]):
            pct = (total / total_income) * 100 if total_income else 0
            c.drawString(margin, y, f"{proc}: ${total:,.2f} ({pct:.1f}%)")
            y -= 16
    return y


def write_basic_summary_pdf(
    debtor_name, summary_path, processor_totals, total_income, linked_accounts, possible_mcas
):
    c = canvas.Canvas(str(summary_path), pagesize=letter)
    width, height = letter
    margin = 40
    y = height - margin

    # Title
    c.setFont("Helvetica-Bold", 18)
    c.drawString(margin, y, f"{debtor_name} - Bank Statement Summary")
    y -= 32

    # Income Sources
    c.setFont("Helvetica-Bold", 12)
    c.drawString(margin, y, "Income Sources Analysis")
    y -= 18
    c.setFont("Helvetica", 12)
    y = write_processor_summary(c, margin, y, processor_totals, total_income)

    # Possible Other MCAs
    c.setFont("Helvetica-Bold", 12)
    c.drawString(margin, y, "Possible Other MCA's")
    y -= 18
    c.setFont("Helvetica", 12)
    if not possible_mcas:
        c.drawString(margin, y, "None found.")
        y -= 16
    else:
        for mca in possible_mcas:
            for line in wrap_pdf_line(mca, width=100):
                c.drawString(margin, y, line)
                y -= 16

    # Linked Accounts
    c.setFont("Helvetica-Bold", 12)
    c.drawString(margin, y, "Linked Accounts (Possible Internal Transfers)")
    y -= 18
    c.setFont("Helvetica", 12)
    y = write_linked_accounts_summary(c, margin, y, linked_accounts)

    c.save()


def wrap_pdf_line(text, width=100):
    import textwrap

    return textwrap.wrap(text, width=width)


if __name__ == "__main__":
    import config

    openai_api_key = config.openai_api_key
    files = sys.argv[1:]
    if not files:
        print("Usage: python bank_analyzer.py file1.pdf [file2.pdf ...]")
        sys.exit(1)
    process_bank_statements_full(files, openai_api_key)
# === Compatibility shim: provide extract_text_from_pdf for ai_analysis ===
# Safe to add even if a similar function already exists.

try:
    import fitz  # PyMuPDF
except Exception as _e:
    fitz = None  # handled below
