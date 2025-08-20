import re
from reportlab.lib.pagesizes import letter
from reportlab.pdfgen import canvas
import openai
try: 
    from bank_analyzer import extract_text_from_pdf
except Exception:
    # Fallbacks if the analyzer exposes different names
    try:
        from bank_analyzer import extract_text as extract_text_from_pdf
# type: ignore 
    except Exception:
        # Last resort: delayed import to avoid hard failure on module import 
        def extract_text_from_pdf(path: str) -> str: 
            from bank_analyzer import extract_text_from_pdf as _impl # may exist at runtime?
            return _imp(path)
import bsa_settings
import os
from collections import defaultdict

def parse_processors_and_accounts(text):
    """
    Gets merchant processors that appear ONLY in deposit/credit/income lines,
    and extracts last 4 account numbers.
    """
    # Expand as needed
    known_processors = set(
        bsa_settings.get_all_merchants() + ["Square", "Stripe", "Intuit", "Coinbase", "Etsy", "PayPal"]
    )
    found_processors = set()
    linked_accounts = set(re.findall(r"\b(\d{4})\b", text))

    # Keywords to identify deposits (feel free to add more!)
    deposit_keywords = ["deposit", "credit", "payment from", "received from", "income", "ach credit"]
    withdrawal_keywords = [
        "withdrawal", "payment to", "purchase", "debit", "withdraw", "sent to", "pos", "atm", "ach debit"
    ]

    for line in text.splitlines():
        line_lower = line.lower()
        # Deposit line if it contains any deposit keyword and does NOT contain any withdrawal keyword
        if any(w in line_lower for w in deposit_keywords) and not any(w in line_lower for w in withdrawal_keywords):
            for proc in known_processors:
                if proc.lower() in line_lower:
                    found_processors.add(proc)

    return list(found_processors), list(linked_accounts)

def sum_deposits_and_accounts(text, processors, accounts):
    """
    Parse the bank statement text and sum totals per processor/account.
    No more dummy data. Now, everything's real!
    """
    processor_totals = {}
    account_totals = {}
    total_income = 0

    # Sum by processor name
    for proc in processors:
        amounts = [float(m.replace(',', '').replace('$', '')) 
                   for m in re.findall(rf"{re.escape(proc)}.*?\$?([\d,]+\.\d\d)", text, re.IGNORECASE)]
        total = round(sum(amounts), 2)
        processor_totals[proc] = total
        total_income += total

    # Optionally sum deposits not matching known processors
    # (Uncomment if you want to track this, or delete if you don't need it)
    """
    other_total = 0
    for m in re.findall(r"deposit.*?\$?([\d,]+\.\d\d)", text, re.IGNORECASE):
        val = float(m.replace(',', '').replace('$', ''))
        if not any(proc.lower() in m.lower() for proc in processors):
            other_total += val
    if other_total > 0:
        processor_totals["Cash/Check/Other"] = round(other_total, 2)
        total_income += other_total
    """

    # Linked accounts: real totals & real direction detection
    for acct in accounts:
        amts = [float(a.replace(',', '').replace('$', '')) 
                for a in re.findall(rf"{acct}.*?\$?([\d,]+\.\d\d)", text)]
        qty = len(amts)
        total = round(sum(amts), 2)
        # Try to determine if deposits or withdrawals
        direction = "Unknown"
        for line in text.splitlines():
            if acct in line:
                l = line.lower()
                if any(word in l for word in ["deposit", "credit", "received", "payment from"]):
                    direction = "In"
                    break
                if any(word in l for word in ["withdrawal", "debit", "payment to", "purchase", "withdraw", "sent to"]):
                    direction = "Out"
                    break
        account_totals[acct] = {"qty": qty, "total": total, "direction": direction}

    return processor_totals, total_income, account_totals

def gpt_extract_entities(pdf_path, openai_api_key, ocr_text):
    """
    Use GPT ONLY to list merchant processors and last 4 account numbers seen in the statement.
    Do not trust it with math!
    """
    prompt = f"""
From the bank statement text below, do NOT provide any totals or percentages.
Just list every merchant processor (like Square, Stripe, Intuit, etc.) and every linked account number (last 4 digits) you see in this statement.
Format as:

Processors:
- [processor name]
- [processor name]
...

LinkedAccounts:
- [last 4 digits]
- [last 4 digits]
...

Bank Statement Text:
{ocr_text}
"""
    openai.api_key = openai_api_key
    response = openai.chat.completions.create(
        model="gpt-4-turbo",
        messages=[{"role": "user", "content": prompt}],
        max_tokens=512,
        temperature=0.1,
    )
    result = response.choices[0].message.content.strip()

    procs = []
    accts = []
    lines = result.splitlines()
    section = None
    for line in lines:
        line = line.strip()
        if not line:
            continue
        if line.lower().startswith("processors:"):
            section = "processors"
            continue
        if line.lower().startswith("linkedaccounts:"):
            section = "accounts"
            continue
        if line.startswith('-') and section == "processors":
            procs.append(line[1:].strip())
        elif line.startswith('-') and section == "accounts":
            accts.append(line[1:].strip())
    return procs, accts

def gpt_analyze_bank_statement(pdf_path, openai_api_key, subfolder):
    company_name = extract_company_name(pdf_path)
    ocr_text = extract_text_from_pdf(pdf_path)

    # Step 1: Use GPT ONLY for entity extraction, not math
    processors, accounts = gpt_extract_entities(pdf_path, openai_api_key, ocr_text)
    # Step 2: Use hardcoded code logic to sum up everything from OCR text
    processor_totals, total_income, account_totals = sum_deposits_and_accounts(ocr_text, processors, accounts)

    summary_filename = f"{company_name} Summary.pdf"
    summary_path = subfolder / summary_filename

    # Section headers (in order)
    section_headers = [
        f"{company_name} - Bank Statement Summary",
        "Income Sources Analysis",
        "Linked Accounts (Last 4 Digits)",
        "Potential Other MCA's",
        "Main Spending Patterns",
        "Questionable or Non-Business Expenses",
        "Evidence of Commingling of Business/Personal Funds",
        "Other Collector-Relevant Insights"
    ]

    # PDF Output
    c = canvas.Canvas(str(summary_path), pagesize=letter)
    width, height = letter
    margin = 40
    y = height - margin

    # Title
    c.setFont("Helvetica-Bold", 18)
    c.drawString(margin, y, section_headers[0])
    y -= 32
    c.setFont("Helvetica", 12)

    # Income Sources Analysis
    c.setFont("Helvetica-Bold", 12)
    c.drawString(margin, y, section_headers[1])
    y -= 18
    c.setFont("Helvetica", 12)
    if not processor_totals:
        c.drawString(margin, y, "None found.")
        y -= 16
    else:
        for proc, total in processor_totals.items():
            percent = f"{round((total/total_income)*100, 1) if total_income else 0}%"
            c.drawString(margin, y, f"{proc}: ${total:,.2f}, {percent}")
            y -= 16

    # Linked Accounts
    c.setFont("Helvetica-Bold", 12)
    c.drawString(margin, y, section_headers[2])
    y -= 18
    c.setFont("Helvetica", 12)
    if not account_totals:
        c.drawString(margin, y, "None found.")
        y -= 16
    else:
        for acct, info in account_totals.items():
            c.drawString(margin, y, f"{acct}: {info['direction']} - Quantity: {info['qty']}, Total: ${info['total']:,.2f}")
            y -= 16

    # The rest: let GPT summarize as before, but only for text analysis
    main_prompt = f"""
    For the bank statement below, summarize (in one concise sentence or phrase per section) the following sections. 
    DO NOT do any math, DO NOT use asterisks or bullets, and ALWAYS prefix each answer with the correct section header exactly as shown below (colon after each).
    If you have no findings for a section, write: None found.

    Potential Other MCA's:
    Main Spending Patterns:
    Questionable or Non-Business Expenses:
    Evidence of Commingling of Business/Personal Funds:
    Other Collector-Relevant Insights:

    Bank Statement Text:
    {ocr_text}
    """

    openai.api_key = openai_api_key
    resp = openai.chat.completions.create(
        model="gpt-4-turbo",
        messages=[{"role": "user", "content": main_prompt}],
        max_tokens=512,
        temperature=0.1,
    )
    result = resp.choices[0].message.content.strip()

    # Parse the result using section headers
    sections = [
        "Potential Other MCA's:",
        "Main Spending Patterns:",
        "Questionable or Non-Business Expenses:",
        "Evidence of Commingling of Business/Personal Funds:",
        "Other Collector-Relevant Insights:",
    ]
    section_dict = {h: "None found." for h in sections}

    for line in result.splitlines():
        line = line.strip()
        for h in sections:
            if line.lower().startswith(h.lower()):
                # Keep only the content after the header
                section_dict[h] = line[len(h):].strip() or "None found."

    # Now output to PDF in correct order
    for i, header in enumerate(section_headers[3:], start=3):
        c.setFont("Helvetica-Bold", 12)
        c.drawString(margin, y, header)
        y -= 18
        c.setFont("Helvetica", 12)
        pdf_section = sections[i-3]  # Map section header to GPT output header
        content = section_dict.get(pdf_section, "None found.")
        for wrapline in wrap_text(content, width=90):
            c.drawString(margin, y, wrapline)
            y -= 16
        if y < margin + 48:
            c.showPage()
            y = height - margin
            c.setFont("Helvetica", 12)

        c.save()
        return str(summary_path)

def clean_for_pdf(text):
    # Remove Markdown, asterisks, underscores, etc.
    text = re.sub(r'\*\*([^\*]+)\*\*', r'\1', text)
    text = re.sub(r'__([^_]+)__', r'\1', text)
    text = text.replace('`', '')
    return text

def wrap_text(text, width=90):
    import textwrap
    return textwrap.wrap(text, width=width)

def process_bank_statements_ai(filepaths, openai_api_key, content_frame=None):
    for pdf_path in filepaths:
        subfolder = get_statement_subfolder(pdf_path)
        summary_path = gpt_analyze_bank_statement(pdf_path, openai_api_key, subfolder)
        # UI update
        if content_frame is not None:
            from customtkinter import CTkLabel
            for widget in content_frame.winfo_children():
                widget.destroy()
            CTkLabel(content_frame, text="AI Statement Analysis Complete!", font=("Arial", 22, "bold"), text_color="#0075c6").pack(pady=(25, 10))
            CTkLabel(content_frame, text=f"Redacted processor pages and summary PDF saved to:\n{subfolder}", font=("Arial", 12), text_color="#333").pack(pady=(10, 2))
            CTkLabel(content_frame, text=f"Latest summary: {os.path.basename(summary_path)}", font=("Arial", 12), text_color="#555").pack(anchor="w", padx=30)

if __name__ == "__main__":
    import sys
    import config
    openai_api_key = config.openai_api_key
    files = sys.argv[1:]
    if not files:
        print("Usage: python ai_analysis.py file1.pdf [file2.pdf ...]")
        sys.exit(1)
    process_bank_statements_ai(files, openai_api_key)