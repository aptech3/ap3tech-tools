import os
import re
from datetime import datetime

import fitz  # PyMuPDF
import pytesseract
from pdf2image import convert_from_path

# --- CATEGORY KEYWORDS ---
UCC_KEYWORDS = [
    "ucc financing statement",
    "form ucc1",
    "secured party",
    "debtor",
    "Adlai Stevenson",
]
CONTRACT_KEYWORDS = ["revenue based financing agreement"]
CLIENT_NOTE_KEYWORDS = [
    "risk note",
    "deal note",
    "refinance note",
    "advance request note",
    "the account status has changed",
]
BANK_STATEMENT_KEYWORDS = [
    "bank of america",
    "chase",
    "wells fargo",
    "td bank",
    "ending balance",
    "available balance",
    "posted transactions",
    "decisionlogic",
    "statement period",
    "account summary",
    "beginning balance",
]

# --- HEURISTICS ---
CONTRACT_PAGE_COUNT = 10
UNIQUE_NOTE_KEYWORDS = [
    "advised",
    "communicated",
    "comm ",
    "response",
    "to me",
    "to collectionsmgt",
    "an sms was received",
    "called",
    "forwarded message",
    "spoke with",
    "sw ",
    "voicemail",
    "vm",
]
EXCLUDE_NOTE_PHRASES = [
    "reaching out every other day",
    "bulk",
    "contact type: called",
    "various channels",
    "@everestbusinessfunding.com",
    "email blast sent",
    "---------- forwarded message --------- from: ",
    "@vadermountainfunding.com",
    "@pmfus.com",
    "@ev-bf.com",
    "@vadermountaincapital.com",
    "@premiummerchantfunding.com",
    "please be advised that a ucc lien fee",
    "@whetstoneholdings.com",
    "@ev-",
    "@machfunding.com",
    "@machcapitalent.com",
    "@teamgccap.com",
    "@trustfi.com",
    "reaching out weekly",
    "dedicated portal update",
    "prompt response",
]
EMAIL_EXCLUSION_PATTERNS = [
    "@everestbusinessfunding.com",
    "@vadermountainfunding.com",
    "@pmfus.com",
    "@ev-bf.com",
    "@vadermountaincapital.com",
    "@premiummerchantfunding.com",
    "@whetstoneholdings.com",
    "@ev-",
    "@machfunding.com",
    "@machcapitalent.com",
    "@teamgccap.com",
    "@trustfi.com",
]

# --- HEADERS TO IGNORE IN HIGHLIGHTING ---
HEADER_LINES = ["POSSIBLE EMAIL ADDRESSES:", "PHONE NUMBERS:", "CLIENT NOTES:"]

# --- COLOR & STYLE RULES ---
COLOR_RULES = [
    {
        "name": "lawyer",
        "pattern": re.compile(r"\\b(atty|aty|attorney|law|lawyer)\\b", re.I),
        "color": (1, 0, 0),  # Red
        "bold": True,
        "italic": True,
        "font_size": 13,
    },
    {
        "name": "comms",
        "pattern": re.compile(
            r"talked to|spoke to|said|answered|hung up|advised|minutes ago|received", re.I
        ),
        "color": (1, 0.55, 0),  # Orange
        "bold": True,
        "italic": True,
        "font_size": 10,
    },
    {
        "name": "money",
        "pattern": re.compile(
            r"(\$\s?\d{1,3}(?:,\d{3})*(?:\.\d{2})?|\\b\d{1,3}(?:,\d{3})*\.\d{2}\b)"
        ),
        "color": (0, 0.5, 0),  # Green
        "bold": True,
        "italic": False,
        "font_size": 13,
    },
    {
        "name": "drc",
        "pattern": re.compile(r"\\bDRC\\b", re.I),
        "color": (0, 0, 1),  # Blue
        "bold": True,
        "italic": True,
        "font_size": 13,
    },
]


def colorize_line(line):
    """
    Apply color, bold, italic, and font size to keywords/matches in a given line.
    Returns a list of tuples: (styled_text, color, bold, italic, font_size, keyword_type)
    """
    results = []
    i = 0
    while i < len(line):
        match_obj = None
        match_rule = None
        for rule in COLOR_RULES:
            match = rule["pattern"].search(line, i)
            if match and (match_obj is None or match.start() < match_obj.start()):
                match_obj = match
                match_rule = rule
        if match_obj and match_obj.start() > i:
            # Non-matching part before (add None for keyword_type)
            results.append((line[i : match_obj.start()], None, False, False, 10, None))
            i = match_obj.start()
        if match_obj:
            results.append(
                (
                    line[match_obj.start() : match_obj.end()],
                    match_rule["color"],
                    match_rule["bold"],
                    match_rule["italic"],
                    match_rule["font_size"],
                    match_rule["name"],  # <--- the type ("comms", "lawyer", etc)
                )
            )
            i = match_obj.end()
        else:
            results.append((line[i:], None, False, False, 10, None))
            break
    return results


# --- MAIN SPLITTING FUNCTION ---
def split_recovery_pdf(filepath, output_dir=None):
    doc = fitz.open(filepath)
    merchant_name = extract_merchant_name(doc)
    if not merchant_name:
        merchant_name = f"UnknownMerchant_{datetime.now().strftime('%Y%m%d_%H%M%S')}"

    save_dir = os.path.join(
        output_dir or os.path.dirname(filepath), title_case_filename(merchant_name)
    )
    os.makedirs(save_dir, exist_ok=True)

    categorized_pages = {
        "ucc": [],
        "contract": [],
        "client_notes_raw": [],
        "bank_statements": [],
        "transaction_history": [],
        "other": [],
    }

    contract_start = next(
        (
            i
            for i, page in enumerate(doc)
            if "revenue based financing agreement" in page.get_text().lower()
        ),
        None,
    )
    contract_pages = (
        list(range(contract_start, contract_start + 10)) if contract_start is not None else []
    )

    recovery_copy_path = os.path.join(
        save_dir, f"{title_case_filename(merchant_name)} Recovery.pdf"
    )
    save_pages_to_pdf(doc, list(range(len(doc))), recovery_copy_path)

    excluded_pages = set(contract_pages)

    for i, page in enumerate(doc):
        if i in excluded_pages:
            continue
        text = page.get_text()
        if not text.strip():
            image = convert_from_path(filepath, first_page=i + 1, last_page=i + 1)[0]
            text = pytesseract.image_to_string(image)
        text = text.lower()
        if "ach works" in text and (
            "employee system" in text or "employeesystem" in text or "employee\nsystem" in text
        ):
            categorized_pages["transaction_history"].append(i)
            continue
        page_type = classify_page(text)
        categorized_pages[page_type].append(i)

    bank_pages = categorized_pages["bank_statements"]
    if bank_pages:
        first = min(bank_pages)
        last = max(bank_pages)
        full_bank_range = list(range(first, last + 1))
        categorized_pages["bank_statements"] = full_bank_range

    if contract_pages:
        last_page_text = doc[contract_pages[-1]].get_text().lower()
        if "class action waiver" in last_page_text and "arbitration" in last_page_text:
            categorized_pages["contract"] = contract_pages
        else:
            filename = f"{title_case_filename(merchant_name)} Contract Incomplete.pdf"
            pdf_path = os.path.join(save_dir, filename)
            save_pages_to_pdf(doc, contract_pages, pdf_path)

    categorized_pages["ucc"] = [p for p in categorized_pages["ucc"] if p not in excluded_pages]

    known_pages = set()
    for cat in ["contract", "ucc", "client_notes_raw", "bank_statements", "transaction_history"]:
        known_pages.update(categorized_pages[cat])
    categorized_pages["other"] = [i for i in range(len(doc)) if i not in known_pages]

    for category, pages in categorized_pages.items():
        if not pages:
            continue
        filename = f"{title_case_filename(merchant_name)} {category.replace('_', ' ').upper() if category == 'ucc' else category.replace('_', ' ').title()}.pdf"
        pdf_path = os.path.join(save_dir, filename)
        save_pages_to_pdf(doc, pages, pdf_path)

    client_note_pages = categorized_pages["client_notes_raw"]
    if client_note_pages:
        parsed_notes = []
        emails = set()
        for i in client_note_pages:
            text = doc[i].get_text()
            lines = text.splitlines()
            for j, line in enumerate(lines):
                line = line.encode("ascii", "ignore").decode("ascii")
                email_matches = re.findall(r"[\w\.-]+@[\w\.-]+", line)
                for email in email_matches:
                    if not any(
                        email.lower().endswith(skip) for skip in EMAIL_EXCLUSION_PATTERNS
                    ) and not any(skip in email.lower() for skip in EMAIL_EXCLUSION_PATTERNS):
                        emails.add(email.lower())
                if any(keyword in line.lower() for keyword in UNIQUE_NOTE_KEYWORDS):
                    if not any(ex in line.lower() for ex in EXCLUDE_NOTE_PHRASES):
                        buffer = "\n".join(lines[j : j + 3])
                        timestamp = extract_datetime_from_text(buffer)
                        parsed_notes.append(f"{timestamp} - {line.strip()}")
        phones = set()
        for note in parsed_notes:
            note_phone_matches = re.findall(r"\(?\d{3}\)?[-.\s]?\d{3}[-.\s]?\d{4}", note)
            for match in note_phone_matches:
                digits = re.sub(r"\D", "", match)
                if len(digits) == 10:
                    phones.add(digits)
        unique_digits = sorted(phones)
        formatted_phones = [f"({p[:3]}) {p[3:6]}-{p[6:]}" for p in unique_digits]

        lines = [
            "POSSIBLE EMAIL ADDRESSES:",
            *[email for email in sorted(emails)],
            "",
            "PHONE NUMBERS:",
            *[phone for phone in formatted_phones],
            "",
            "CLIENT NOTES:",
            *[note for note in parsed_notes],
        ]

        notes_output_path = os.path.join(
            save_dir, f"{title_case_filename(merchant_name)} Client Notes Parsed.pdf"
        )
        render_colored_pdf(lines, notes_output_path)
    return save_dir


def render_colored_pdf(lines, output_path):
    doc = fitz.open()
    margin = 72
    width, height = fitz.paper_size("letter")
    max_width = width - 2 * margin
    y = margin
    page = doc.new_page()
    for line in lines:
        is_header = line.strip().upper() in HEADER_LINES
        if is_header:
            font_size = 14
            font_name = "helv"
            color = (0, 0, 0)
            run = [(line, color, False, False, font_size, font_name)]
        else:
            run = []
            for text, color, bold, italic, font_size, keyword_type in colorize_line(
                line
            ):  # note extra return
                # Only bump font size for money/lawyer/DRC, not comms (orange)
                if keyword_type == "comms":
                    eff_size = font_size  # no size bump for comms/orange
                elif bold and italic:
                    eff_size = font_size + 4
                elif bold or italic:
                    eff_size = font_size + 2
                else:
                    eff_size = font_size
                font_name = "helv"
                run.append((text, color, bold, italic, eff_size, font_name))
        x = margin
        for text, color, bold, italic, font_size, font_name in run:
            if color is None:
                color = (0, 0, 0)
            # Wrap text if it exceeds line width
            if (
                fitz.get_text_length(text, fontsize=font_size, fontname=font_name) + x
                > margin + max_width
            ):
                y += font_size + 2
                x = margin
            page.insert_text((x, y), text, fontsize=font_size, fontname=font_name, color=color)
            x += fitz.get_text_length(text, fontsize=font_size, fontname=font_name)
        y += 16 if not is_header else 20
        if y > height - margin:
            page = doc.new_page()
            y = margin
    doc.save(output_path)
    doc.close()


def extract_merchant_name(doc):
    first_page_text = doc[0].get_text()
    match = re.search(r"Business Name:\s*([^\n]+)", first_page_text, re.IGNORECASE)
    if match:
        return sanitize_filename(match.group(1).strip())
    return None


def sanitize_filename(name):
    return re.sub(r'[\\/*?:"<>|]', "", name)


def title_case_filename(name):
    acronyms = {"LLC", "INC", "CORP", "DBA", "NYC", "USA", "LLP", "TV"}
    words = name.split()
    result = []
    for word in words:
        clean = re.sub(r"[^a-zA-Z]", "", word)
        if clean.upper() in acronyms:
            result.append(word.upper())
        else:
            result.append(word.capitalize())
    return " ".join(result)


def classify_page(text):
    text = text.lower()
    if any(term in text for term in CLIENT_NOTE_KEYWORDS):
        return "client_notes_raw"
    if any(k in text for k in UCC_KEYWORDS):
        return "ucc"
    contract_hits = sum(1 for k in CONTRACT_KEYWORDS if k in text)
    if contract_hits >= 1:
        return "contract"
    bank_hits = sum(1 for k in BANK_STATEMENT_KEYWORDS if k in text)
    if bank_hits >= 2:
        return "bank_statements"
    return "other"


def save_pages_to_pdf(doc, page_numbers, output_path):
    new_doc = fitz.open()
    for page_num in sorted(page_numbers):
        new_doc.insert_pdf(doc, from_page=page_num, to_page=page_num)
    new_doc.save(output_path)
    new_doc.close()


def extract_datetime_from_text(text):
    match = re.search(r"(\d{1,2}/\d{1,2}/\d{4})[\s\n]+(\d{1,2}:\d{2}\s?(AM|PM|am|pm))", text)
    if match:
        return f"{match.group(1)}"
    match = re.search(r"(\d{1,2}/\d{1,2}/\d{4})", text)
    if match:
        return match.group(1)
    return ""


HIGHLIGHT_KEYWORDS = [
    "talked to",
    "spoke to",
    "said",
    "answered",
    "hung up",
    "advised",
    "minutes ago",
    "received",
]

DATE_PATTERN = re.compile(r"(\d{1,2}/\d{1,2}/\d{4})")


def highlight_notes_in_pdf(doc, page_num):
    page = doc[page_num]
    blocks = page.get_text("blocks")

    # Store (y, text, rect) for each block
    line_data = [
        (b[1], b[4].strip(), fitz.Rect(b[:4])) for b in blocks if len(b) >= 5 and b[4].strip()
    ]
    line_data.sort()  # sort top-to-bottom

    lines = [t for _, t, _ in line_data]
    rects = [r for _, _, r in line_data]

    highlight_ranges = []
    date_lines = [i for i, line in enumerate(lines) if DATE_PATTERN.search(line)]

    for i, line in enumerate(lines):
        # SKIP HEADER LINES
        if line.strip().upper() in HEADER_LINES:
            continue
        if any(kw in line.lower() for kw in HIGHLIGHT_KEYWORDS):
            start = max([d for d in date_lines if d <= i], default=0)
            end = next((d for d in date_lines if d > i), len(lines))
            highlight_ranges.append((start, end))

    for start, end in highlight_ranges:
        highlighted_indices = set()  # Track lines we've highlighted this pass
        for i in range(start, end):
            if i in highlighted_indices:
                continue
            if rects[i] and lines[i].strip() and lines[i].strip().upper() not in HEADER_LINES:
                highlight = page.add_highlight_annot(rects[i])
                highlight.set_colors(stroke=(1, 1, 0))
                highlight.update()
                highlighted_indices.add(i)

    return doc
