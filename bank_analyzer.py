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
from typing import Callable, Optional

# Heuristic header matcher: exact token first, fuzzy only for short lines
def _matches_header_text(s: str, phrases: list) -> bool:
    s_low = s.strip().lower()
    def _has_token(p: str) -> bool:
        p = p.lower()
        # For short tokens like 'atm', 'pos', require whole-word match to avoid false positives
        if len(p) <= 3 and all(ch.isalpha() for ch in p):
            return re.search(r"\b" + re.escape(p) + r"s?\b", s_low) is not None
        return p in s_low
    if any(_has_token(p) for p in phrases):
        return True
    if len(s_low) <= 40:  # avoid fuzzy on long sentences (e.g., banner notices)
        for p in phrases:
            try:
                if fuzz.ratio(s_low, p) >= 90:
                    return True
            except Exception:
                continue
    return False

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
    # Fall back to system Poppler (None lets pdf2image use PATH on Linux/macOS)
    return None


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
    deposit_keywords = [
        "deposit", "credit", "payment from", "received from", "income", "ach credit"
    ]
    withdrawal_keywords = [
        "withdrawal", "payment to", "purchase", "debit", "withdraw", "sent to", "pos", "atm", "ach debit", "fee"
    ]
    depos_headers = [
        "deposits", "deposit ", "credits", "deposits and credits", "deposit and other credits",
        "deposits & other credits", "credits posted", "electronic credits",
        "incoming transfer", "direct deposit", "mobile deposit", "check deposit", "cash deposit",
        "other credits", "total deposits", "ach credits"
    ]
    withdr_headers = [
        "withdrawals", "debits", "withdrawals and debits", "debits and other withdrawals",
        "ach debit", "card purchases", "fees", "checks"
    ]

    def _is_deposit_line(line_lower: str, current_section: Optional[str]) -> bool:
        if current_section == 'dep':
            return True
        # Fallback heuristic if no section detected
        has_dep = any(w in line_lower for w in deposit_keywords)
        has_wd = any(w in line_lower for w in withdrawal_keywords)
        if has_dep and not has_wd:
            return True
        # final fallback: positive amount and no withdrawal keywords
        has_pos_amount = any(
            not a.replace(',', '').strip().startswith('-')
            for a in re.findall(r"\$?(-?[\d,]+\.\d\d)", line_lower)
        )
        return has_pos_amount and not has_wd

    try:
        reader = PyPDF2.PdfReader(pdf_path)
        for i, page in enumerate(reader.pages):
            text = page.extract_text() or ""
            current_section = None
            for line in text.splitlines():
                line_lower = line.lower()
                if any(h in line_lower for h in depos_headers) or any(
                    fuzz.ratio(line_lower, h) >= 85 for h in depos_headers
                ):
                    current_section = 'dep'
                    continue
                if any(h in line_lower for h in withdr_headers) or any(
                    fuzz.ratio(line_lower, h) >= 85 for h in withdr_headers
                ):
                    current_section = 'wd'
                    continue
                if not _is_deposit_line(line_lower, current_section):
                    continue

                # KNOWN merchant processors
                for keyword in merchant_keywords:
                    keyword_lower = keyword.lower()
                    if (
                        keyword_lower in line_lower
                        and keyword_lower not in seen_normalized
                    ):
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
    deposit_keywords = [
        "deposit", "credit", "payment from", "received from", "income", "ach credit"
    ]
    withdrawal_keywords = [
        "withdrawal", "payment to", "purchase", "debit", "withdraw", "sent to", "pos", "atm", "ach debit", "fee"
    ]
    depos_headers = [
        "deposits", "deposit ", "credits", "deposits and credits", "deposit and other credits",
        "deposits & other credits", "credits posted", "electronic credits",
        "incoming transfer", "direct deposit", "mobile deposit", "check deposit", "cash deposit",
        "other credits", "total deposits", "ach credits"
    ]
    withdr_headers = [
        "withdrawals", "debits", "withdrawals and debits", "debits and other withdrawals",
        "ach debit", "card purchases", "fees", "checks"
    ]

    def _is_deposit_line(line_lower: str, current_section: Optional[str]) -> bool:
        if current_section == 'dep':
            return True
        has_dep = any(w in line_lower for w in deposit_keywords)
        has_wd = any(w in line_lower for w in withdrawal_keywords)
        if has_dep and not has_wd:
            return True
        has_pos_amount = any(
            not a.replace(',', '').strip().startswith('-')
            for a in re.findall(r"\$?(-?[\d,]+\.\d\d)", line_lower)
        )
        return has_pos_amount and not has_wd

    try:
        reader = PyPDF2.PdfReader(pdf_path)
        for i, page in enumerate(reader.pages):
            text = page.extract_text() or ""
            current_section = None
            for line in text.splitlines():
                line_lower = line.lower()
                if _matches_header_text(line_lower, depos_headers):
                    current_section = 'dep'
                    continue
                if _matches_header_text(line_lower, withdr_headers):
                    current_section = 'wd'
                    continue
                if not _is_deposit_line(line_lower, current_section):
                    continue

                # KNOWN merchant processors
                for keyword in merchant_keywords:
                    keyword_lower = keyword.lower()
                    # Exclusion check for known keywords
                    if (
                        keyword_lower in line_lower
                        and keyword_lower not in seen_normalized
                    ):
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
        filename = f"{company_name} {safe_processor} p{page_num + 1}.pdf"
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
    """
    Extract text from a PDF. Honors env var BANK_OCR_FIRST=1 to run OCR first.
    Fallback order:
      - If BANK_OCR_FIRST=1: OCR, then pdf text
      - Else: pdf text, then OCR
    """
    import pdfplumber
    import pytesseract

    def _ocr_all_pages() -> str:
        poppler_path = get_poppler_path()
        images = convert_from_path(pdf_path, poppler_path=poppler_path)
        ocr_text_local = ""
        for img in images:
            try:
                ocr_cfg = os.getenv("BANK_OCR_CONFIG", "--psm 6")
                ocr_text_local += pytesseract.image_to_string(img, config=ocr_cfg) + "\n"
            except Exception:
                ocr_text_local += pytesseract.image_to_string(img) + "\n"
        return ocr_text_local

    def _pdf_text() -> str:
        try:
            with pdfplumber.open(pdf_path) as pdf:
                return "\n".join(page.extract_text() or "" for page in pdf.pages)
        except Exception:
            return ""

    ocr_first = os.getenv("BANK_OCR_FIRST") == "1"
    if ocr_first:
        try:
            text = _ocr_all_pages()
            if text.strip():
                return text
        except Exception:
            pass
        text2 = _pdf_text()
        return text2
    else:
        text = _pdf_text()
        if text.strip():
            return text
        try:
            return _ocr_all_pages()
        except Exception:
            return text


def process_bank_statements_full(filepaths, content_frame=None, progress_cb: Optional[Callable[[str], None]] = None):
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

    total_files = len(filepaths)
    for idx, pdf_path in enumerate(filepaths, start=1):
        if progress_cb:
            try:
                progress_cb(f"Processing {idx}/{total_files}: {os.path.basename(pdf_path)}")
            except Exception:
                pass
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
            processor_clean = (
                processor.replace("Possible Processor - ", "").lower().strip()
            )
            if is_excluded(processor_clean):
                continue
            processor_matches[processor] = page_num

        save_processor_pages(pdf_path, processor_matches, subfolder)

        # --- BASIC SUMMARY SECTION ---
        if progress_cb:
            try:
                progress_cb("Extracting text…")
            except Exception:
                pass
        text = extract_text_from_pdf(pdf_path)

        # Debug: detect and save headers seen in OCR/text
        try:
            headers_report = detect_section_headers(text)
            debug_path = subfolder / f"{debtor_name} Headers Debug.txt"
            with open(debug_path, "w", encoding="utf-8") as f:
                f.write("Detected Deposit Headers:\n")
                for h in headers_report["deposit"][:10]:
                    f.write(f"- {h}\n")
                f.write("\nDetected Withdrawal Headers:\n")
                for h in headers_report["withdrawal"][:10]:
                    f.write(f"- {h}\n")
                f.write("\nOther Header-Like Lines:\n")
                for h in headers_report["other"][:10]:
                    f.write(f"- {h}\n")
            if progress_cb:
                try:
                    progress_cb("Analyzing deposits and linked accounts…")
                except Exception:
                    pass
        except Exception:
            pass

        # Merchant processor summary: one line per processor, total and %
        # (Optionally skip exclusions here too, for extra thoroughness)
        filtered_processors = [
            proc for proc in merchant_keywords if not is_excluded(proc)
        ]
        processor_totals, total_income, deposit_debug_lines = summarize_processors(text, filtered_processors)

        # Linked accounts: only ones mentioned on transfer/ACH-type lines
        linked_accounts = summarize_linked_accounts(text)

        # Possible MCAs
        possible_mcas = find_possible_mcas(text)

        summary_pdf = subfolder / f"{debtor_name} Summary.pdf"
        write_basic_summary_pdf(
            debtor_name,
            summary_pdf,
            processor_totals,
            total_income,
            linked_accounts,
            possible_mcas,
        )
        # Write deposit lines debug for diagnostics
        try:
            dep_dbg = subfolder / f"{debtor_name} Deposit Lines Debug.txt"
            with open(dep_dbg, "w", encoding="utf-8") as f:
                for ln in deposit_debug_lines[:300]:
                    f.write(ln + "\n")
        except Exception:
            pass
        if progress_cb:
            try:
                progress_cb(f"Saved summary: {os.path.basename(summary_pdf)}")
            except Exception:
                pass


def detect_section_headers(text: str):
    """Return a dict with detected deposit/withdrawal headers and other header-like lines.
    Uses exact token matching, and only applies fuzzy matching to short lines to avoid false positives
    like banner notices.
    """
    depos_headers = [
        "deposits", "deposit ", "deposits/credits", "credits", "credits (+)",
        "deposits and credits", "deposit and other credits",
        "deposits & other credits", "credits posted", "electronic credits",
        "incoming transfer", "direct deposit", "mobile deposit", "check deposit", "cash deposit",
        "other deposits", "customer deposits", "total customer deposits",
        "other credits", "total deposits", "ach credits"
    ]
    withdr_headers = [
        "withdrawals", "withdrawal", "withdrawals/debits", "debits", "debits (-)",
        "withdrawals and debits", "debits and other withdrawals",
        "debits & other withdrawals", "ach debit", "card purchases", "fees", "checks", "bill pay"
    ]

    deposits_found = []
    withdrawals_found = []
    header_like = []

    for raw in text.splitlines():
        s = raw.strip()
        if not s:
            continue
        low = s.lower()
        # direct token or short-line fuzzy match
        if _matches_header_text(low, depos_headers):
            if s not in deposits_found:
                deposits_found.append(s)
            continue
        if _matches_header_text(low, withdr_headers):
            if s not in withdrawals_found:
                withdrawals_found.append(s)
            continue
        # header-like heuristic: mostly uppercase words, few digits, reasonable length, contains vowels
        if 4 <= len(s) <= 64:
            letters = sum(ch.isalpha() for ch in s)
            uppers = sum(ch.isupper() for ch in s)
            digits = sum(ch.isdigit() for ch in s)
            vowels = sum(ch.lower() in "aeiou" for ch in s)
            if letters > 0 and uppers / max(1, letters) >= 0.6 and digits / max(1, len(s)) < 0.2 and vowels > 0:
                if s not in header_like:
                    header_like.append(s)

    return {"deposit": deposits_found, "withdrawal": withdrawals_found, "other": header_like}


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
    """
    Sum deposits per processor only (ignore withdrawals/fees).
    If the text appears to be a Berkshire Bank statement, use a bank-specific parser
    tuned for the "Date Description Additions Subtractions Balance" layout.
    Otherwise, use a generic, section-aware heuristic that is robust to two-column layouts.
    """
    # Bank-specific fast-paths
    if detect_berkshire_bank(text):
        return _summarize_processors_berkshire(text, known_processors)
    if detect_us_bank(text):
        return _summarize_processors_us_bank(text, known_processors)

    # -------------------- Generic heuristic (fallback) --------------------
    processor_totals = {}
    total_income = 0.0

    depos_headers = [
        "deposits", "deposit ", "credits", "deposits and credits", "deposit and other credits",
        "deposits & other credits", "credits posted", "electronic credits",
        "incoming transfer", "direct deposit", "mobile deposit", "check deposit", "cash deposit",
        "other credits", "total deposits", "ach credits"
    ]
    withdr_headers = [
        "withdrawals", "debits", "withdrawals and debits", "debits and other withdrawals",
        "debits & other withdrawals", "ach debit", "card purchases", "fees", "checks",
        "other debits", "electronic debits", "bill pay"
    ]
    deposit_keywords = [
        "deposit", "credit", "ach credit", "incoming transfer", "direct deposit", "refund"
    ]
    withdrawal_keywords = [
        "withdrawal", "debit", "ach debit", "purchase", "pos", "atm", "check", "fee", "bill pay"
    ]
    balance_markers = ["balance", "subtotal", "total "]

    def _is_header(line: str, keys: list) -> bool:
        # Use the module-level matcher to avoid false positives on long sentences
        return _matches_header_text(line, keys)

    current_section = None  # 'dep' | 'wd' | None
    lines = text.splitlines()
    for proc in known_processors:
        processor_totals[proc] = 0.0

    counted_lines_debug = []

    for raw in lines:
        line = raw.strip()
        low = line.lower()
        if not line:
            continue
        if _is_header(line, depos_headers):
            current_section = 'dep'
            continue
        if _is_header(line, withdr_headers):
            current_section = 'wd'
            continue
        if any(b in low for b in balance_markers):
            # avoid balance/total lines
            continue

        # Only consider deposit lines: either in deposit section or line-level deposit terms present
        in_deposit_context = (
            current_section == 'dep' or (
                current_section is None and any(k in low for k in deposit_keywords) and not any(k in low for k in withdrawal_keywords)
            )
        )
        if not in_deposit_context:
            continue

        # Extract amounts; respect parentheses or minus as negative; keep only positives
        amts_raw = re.findall(r"\$?\s*(\(?-?[\d,]+\.\d\d\)?)", line)
        if not amts_raw:
            continue
        amounts_pos = []
        for a in amts_raw:
            s = a.strip()
            neg = s.startswith('-') or s.endswith(')')
            try:
                val = float(s.replace('(', '').replace(')', '').replace(',', '').replace('$', ''))
            except Exception:
                continue
            if not neg and val > 0:
                amounts_pos.append(val)
        if not amounts_pos:
            continue
        # Prefer the LEFTMOST positive amount (credit column) to avoid picking running balance
        amount_for_line = None
        for a in re.finditer(r"\$?\s*(\(?-?[\d,]+\.\d\d\)?)", line):
            s = a.group(1).strip()
            neg = s.startswith('-') or s.endswith(')')
            try:
                val = float(s.replace('(', '').replace(')', '').replace(',', '').replace('$', ''))
            except Exception:
                continue
            if not neg and val > 0:
                amount_for_line = val
                break
        if amount_for_line is None:
            amount_for_line = min(amounts_pos) if amounts_pos else None
        if amount_for_line is None:
            continue

        matched_any = False
        for proc in known_processors:
            if proc.lower() in low:
                processor_totals[proc] += amount_for_line
                matched_any = True
        if matched_any:
            counted_lines_debug.append(f"{line}  -> +${amount_for_line:,.2f}")

    processor_totals = {k: round(v, 2) for k, v in processor_totals.items() if v > 0}
    total_income = round(sum(processor_totals.values()), 2)
    # Return debug lines so callers can write a debug file when needed
    return processor_totals, total_income, counted_lines_debug


def detect_berkshire_bank(text: str) -> bool:
    t = text.lower()
    if "berkshire bank" in t or "berkshirebank.com" in t:
        return True
    # Header row clue
    if all(k in t for k in ["date", "description", "additions", "subtractions", "balance"]):
        return True
    return False


def _summarize_processors_berkshire(text: str, known_processors):
    """Berkshire Bank layout: rows typically like
    MM-DD <desc possibly with #ACH Credit / #Deposit / #POS Purchase> <amount> <balance>
    We take the first positive amount on each row as the deposit/credit and ignore negatives/parentheses.
    """
    processor_totals = {p: 0.0 for p in known_processors}
    counted_lines_debug = []

    date_row = re.compile(r"^\s*\d{2}[-/]\d{2}\b")
    money_find = re.compile(r"\$?\s*(\(?-?[\d,]+\.\d\d\)?)")

    for raw in text.splitlines():
        line = raw.strip()
        if not line or not date_row.match(line):
            continue
        low = line.lower()
        # Extract all money fields on the row
        amts = money_find.findall(line)
        if not amts:
            continue
        # Choose first positive amount (deposit/credit column)
        amount = None
        for token in amts:
            s = token.strip()
            neg = s.startswith('-') or s.endswith(')')
            try:
                val = float(s.replace('(', '').replace(')', '').replace(',', '').replace('$', ''))
            except Exception:
                continue
            if not neg and val > 0:
                amount = val
                break
        if amount is None:
            continue

        matched = False
        for proc in known_processors:
            if proc.lower() in low:
                processor_totals[proc] += amount
                matched = True
        if matched:
            counted_lines_debug.append(f"{line}  -> +${amount:,.2f}")

    processor_totals = {k: round(v, 2) for k, v in processor_totals.items() if v > 0}
    total_income = round(sum(processor_totals.values()), 2)
    return processor_totals, total_income, counted_lines_debug


def detect_us_bank(text: str) -> bool:
    t = text.lower()
    if "u.s. bank" in t or "us bank" in t or "usbank.com" in t or "usbank" in t:
        return True
    # Headers commonly seen
    if ("deposits/credits" in t and "withdrawals/debits" in t) or ("credits (+)" in t and "debits (-)" in t):
        return True
    return False


def _summarize_processors_us_bank(text: str, known_processors):
    """U.S. Bank style rows often include MM/DD and separate credit/debit columns
    labeled Deposits/Credits and Withdrawals/Debits, or Credits (+)/Debits (-).
    We treat the first positive money token on each row as the credit and ignore negatives.
    """
    processor_totals = {p: 0.0 for p in known_processors}
    counted_lines_debug = []

    # Date patterns occasionally include year or month name; accept both
    date_row_num = re.compile(r"^\s*\d{2}[/-]\d{2}(?:[/-]\d{2,4})?\b")
    date_row_mon = re.compile(r"^\s*(jan|feb|mar|apr|may|jun|jul|aug|sep|oct|nov|dec)[a-z]*\s+\d{1,2}\b", re.I)
    money_find = re.compile(r"\$?\s*(\(?-?[\d,]+\.\d\d\)?)")
    ignore_section_markers = [
        "analysis service charge detail",
        "service activity detail",
        "balance summary",
        "account summary",
        "balances only appear for days reflecting change",
        "subtotal:",
        "total customer deposits",
        "customer deposits",
        "other deposits",
        "fee based service charges",
        "avg unit price",
        "volume",
    ]

    for raw in text.splitlines():
        line = raw.strip()
        if not line:
            continue
        low = line.lower()
        # Skip non-transaction sections commonly present on U.S. Bank statements (fees/analysis summaries)
        if any(k in low for k in ignore_section_markers):
            continue
        if not (date_row_num.match(line) or date_row_mon.match(line)):
            continue
        # low already computed
        amts = money_find.findall(line)
        if not amts:
            continue
        # choose first positive token (credit column)
        amount = None
        for token in amts:
            s = token.strip()
            neg = s.startswith('-') or s.endswith(')')
            try:
                val = float(s.replace('(', '').replace(')', '').replace(',', '').replace('$', ''))
            except Exception:
                continue
            if not neg and val > 0:
                amount = val
                break
        if amount is None:
            continue

        matched = False
        for proc in known_processors:
            if proc.lower() in low:
                processor_totals[proc] += amount
                matched = True
        if matched:
            counted_lines_debug.append(f"{line}  -> +${amount:,.2f}")

    processor_totals = {k: round(v, 2) for k, v in processor_totals.items() if v > 0}
    total_income = round(sum(processor_totals.values()), 2)
    return processor_totals, total_income, counted_lines_debug


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
    debtor_name,
    summary_path,
    processor_totals,
    total_income,
    linked_accounts,
    possible_mcas,
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
    import os

    # Grab the key from environment variable
    openai_api_key = os.getenv("OPENAI_API_KEY")
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
