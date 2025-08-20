# ai_analysis.py
from __future__ import annotations

import os
import re
from pathlib import Path
from typing import Any, Callable, Dict, Iterable, List, Optional, Tuple

import openai
from reportlab.lib.pagesizes import letter
from reportlab.pdfgen import canvas


# --- Locate project extractor safely (no conditional redefs, no type: ignore) ---
def _get_bank_extractor() -> Optional[Callable[[str], str]]:
    """Return bank_analyzer.extract_text_from_pdf or extract_text if available."""
    try:
        import bank_analyzer  # mypy: treated as Any due to ignore_missing_imports in config
    except Exception:
        return None
    func = getattr(bank_analyzer, "extract_text_from_pdf", None)
    if callable(func):
        return func
    func2 = getattr(bank_analyzer, "extract_text", None)
    if callable(func2):
        return func2
    return None


def extract_text_from_pdf(path: str) -> str:
    """
    Text extractor for bank statements.
    Uses project implementation if present; else falls back to PyMuPDF.
    """
    bank_fn = _get_bank_extractor()
    if bank_fn is not None:
        try:
            return bank_fn(path)
        except Exception:
            # fall back to local extractor if project one fails at runtime
            pass

    try:
        import fitz  # PyMuPDF

        parts: List[str] = []
        with fitz.open(path) as doc:
            for p in doc:
                parts.append(p.get_text("text"))
        return "\n".join(parts)
    except Exception:
        return ""


def _get_known_processors() -> List[str]:
    """
    Merge a small base list with optional bsa_settings.get_all_merchants().
    """
    base = ["Square", "Stripe", "Intuit", "Coinbase", "Etsy", "PayPal"]
    try:
        import bsa_settings  # mypy: treated as Any due to ignore_missing_imports

        if hasattr(bsa_settings, "get_all_merchants"):
            extra = bsa_settings.get_all_merchants()
            if isinstance(extra, list):
                return sorted(set(base + extra))
    except Exception:
        pass
    return base


def extract_company_name(pdf_path: str) -> str:
    """Best-effort company name from filename stem."""
    stem = Path(pdf_path).stem
    tokens = re.split(r"[\s_\-]+", stem)
    for t in tokens:
        if re.search(r"[A-Za-z]", t):
            return t
    return stem or "Unknown"


def get_statement_subfolder(pdf_path: str) -> Path:
    """
    Create/return an output folder alongside the PDF, e.g.:
    /path/to/Statement_Aug.pdf -> /path/to/Statement_Aug_analysis/
    """
    p = Path(pdf_path).resolve()
    out = p.with_suffix("")
    out = out.parent / f"{out.name}_analysis"
    out.mkdir(parents=True, exist_ok=True)
    return out


def wrap_text(text: str, width: int = 90) -> List[str]:
    import textwrap

    return textwrap.wrap(text, width=width)


def clean_for_pdf(text: str) -> str:
    """Remove simple Markdown emphases/backticks for clean PDF output."""
    text = re.sub(r"\*\*([^\*]+)\*\*", r"\1", text)
    text = re.sub(r"__([^_]+)__", r"\1", text)
    return text.replace("`", "")


def _chat_completion(
    api_key: str,
    model: str,
    messages: List[Dict[str, Any]],
    max_tokens: int = 512,
    temperature: float = 0.1,
):
    """Version-tolerant wrapper around OpenAI Chat Completions API (no ignores)."""
    # Newer SDK (client) path
    if hasattr(openai, "OpenAI"):
        client = openai.OpenAI(api_key=api_key)
        return client.chat.completions.create(
            model=model,
            messages=messages,
            max_tokens=max_tokens,
            temperature=temperature,
        )
    # Legacy SDK path via getattr to avoid attribute-check errors in mypy
    openai.api_key = api_key
    chat_cls = getattr(openai, "ChatCompletion", None)
    if chat_cls is not None and hasattr(chat_cls, "create"):
        return chat_cls.create(
            model=model,
            messages=messages,
            max_tokens=max_tokens,
            temperature=temperature,
        )
    raise RuntimeError(
        "OpenAI Chat Completions unavailable: SDK missing both client and legacy API"
    )


# --- Parsing & tally logic (code does the math; GPT only extracts entities) ----
def parse_processors_and_accounts(text: str) -> Tuple[List[str], List[str]]:
    """
    From raw statement text:
      - Find merchant processors that appear in deposit/credit/income lines (not withdrawals).
      - Extract linked account last-4s (simple 4-digit sequences).
    """
    known_processors = set(_get_known_processors())
    found_processors: set[str] = set()
    linked_accounts = set(re.findall(r"\b(\d{4})\b", text))

    deposit_keywords = [
        "deposit",
        "credit",
        "payment from",
        "received from",
        "income",
        "ach credit",
    ]
    withdrawal_keywords = [
        "withdrawal",
        "payment to",
        "purchase",
        "debit",
        "withdraw",
        "sent to",
        "pos",
        "atm",
        "ach debit",
    ]

    for line in text.splitlines():
        line_lower = line.lower()
        if any(w in line_lower for w in deposit_keywords) and not any(
            w in line_lower for w in withdrawal_keywords
        ):
            for proc in known_processors:
                if proc.lower() in line_lower:
                    found_processors.add(proc)

    return sorted(found_processors), sorted(linked_accounts)


def sum_deposits_and_accounts(
    text: str, processors: Iterable[str], accounts: Iterable[str]
) -> Tuple[Dict[str, float], float, Dict[str, Dict[str, Any]]]:
    """
    Sum totals per processor (strictly by name occurrence) and per account last-4.
    Returns: (processor_totals, total_income, account_totals)
    """
    processor_totals: Dict[str, float] = {}
    account_totals: Dict[str, Dict[str, Any]] = {}
    total_income = 0.0

    # Sum by processor
    for proc in processors:
        pattern = rf"{re.escape(proc)}.*?\$?([\d,]+\.\d\d)"
        amounts = [
            float(m.replace(",", "").replace("$", "")) for m in re.findall(pattern, text, re.I)
        ]
        total = round(sum(amounts), 2)
        processor_totals[proc] = total
        total_income += total

    # Sum by account (last-4)
    for acct in accounts:
        amts = [
            float(a.replace(",", "").replace("$", ""))
            for a in re.findall(rf"{re.escape(acct)}.*?\$?([\d,]+\.\d\d)", text)
        ]
        qty = len(amts)
        total = round(sum(amts), 2)

        direction = "Unknown"
        for line in text.splitlines():
            if acct in line:
                line_lower = line.lower()
                if any(w in line_lower for w in ["deposit", "credit", "received", "payment from"]):
                    direction = "In"
                    break
                if any(
                    w in line_lower
                    for w in ["withdrawal", "debit", "payment to", "purchase", "sent to"]
                ):
                    direction = "Out"
                    break

        account_totals[acct] = {"qty": qty, "total": total, "direction": direction}

    return processor_totals, total_income, account_totals


# --- GPT: only for entity extraction & narrative summaries ---------------------
_DEF_MODEL = "gpt-4-turbo"  # change to "gpt-4o-mini" if preferred


def gpt_extract_entities(openai_api_key: str, ocr_text: str) -> Tuple[List[str], List[str]]:
    """Use GPT ONLY to list merchant processors and account last-4s seen in the statement."""
    prompt = (
        "From the bank statement text below, do NOT provide any totals or percentages.\n"
        "Just list every merchant processor (like Square, Stripe, Intuit, etc.) and every "
        "linked account number (last 4 digits) you see in this statement.\n"
        "Format as:\n\n"
        "Processors:\n"
        "- [processor name]\n"
        "- [processor name]\n"
        "...\n\n"
        "LinkedAccounts:\n"
        "- [last 4 digits]\n"
        "- [last 4 digits]\n"
        "...\n\n"
        "Bank Statement Text:\n"
        f"{ocr_text}\n"
    )

    resp = _chat_completion(
        api_key=openai_api_key,
        model=_DEF_MODEL,
        messages=[{"role": "user", "content": prompt}],
        max_tokens=512,
        temperature=0.1,
    )

    # Compatible access for both new/old SDKs
    result: str = ""
    choices = getattr(resp, "choices", None)
    if choices:
        msg = getattr(choices[0], "message", None)
        if msg and hasattr(msg, "content"):
            result = str(msg.content or "")
    if not result and isinstance(resp, dict) and "choices" in resp:
        try:
            result = resp["choices"][0]["message"]["content"]  # legacy dict-like
        except Exception:
            result = ""

    procs: List[str] = []
    accts: List[str] = []
    section = None
    for line in result.splitlines():
        s = line.strip()
        if not s:
            continue
        low = s.lower()
        if low.startswith("processors:"):
            section = "processors"
            continue
        if low.startswith("linkedaccounts:"):
            section = "accounts"
            continue
        if s.startswith("-") and section == "processors":
            procs.append(s[1:].strip())
        elif s.startswith("-") and section == "accounts":
            accts.append(s[1:].strip())
    return procs, accts


def gpt_analyze_bank_statement(pdf_path: str, openai_api_key: str, subfolder: Path) -> str:
    company_name = extract_company_name(pdf_path)
    ocr_text = extract_text_from_pdf(pdf_path)

    # 1) GPT finds entities only
    processors, accounts = gpt_extract_entities(openai_api_key, ocr_text)

    # 2) Code does the math
    processor_totals, total_income, account_totals = sum_deposits_and_accounts(
        ocr_text, processors, accounts
    )

    summary_filename = f"{company_name} Summary.pdf"
    summary_path = subfolder / summary_filename

    # Section headers (display order)
    section_headers = [
        f"{company_name} - Bank Statement Summary",
        "Income Sources Analysis",
        "Linked Accounts (Last 4 Digits)",
        "Potential Other MCA's",
        "Main Spending Patterns",
        "Questionable or Non-Business Expenses",
        "Evidence of Commingling of Business/Personal Funds",
        "Other Collector-Relevant Insights",
    ]

    # ---- PDF Output -----------------------------------------------------------
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
            pct = f"{round((total / total_income) * 100, 1) if total_income else 0}%"
            c.drawString(margin, y, f"{proc}: ${total:,.2f}, {pct}")
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
            line = f"{acct}: {info['direction']} - Quantity: {info['qty']}, Total: ${info['total']:,.2f}"
            c.drawString(margin, y, line)
            y -= 16

    # Narrative sections (GPT text only; no math)
    main_prompt = (
        "For the bank statement below, summarize (in one concise sentence or phrase per section) the "
        "following sections.\n"
        "DO NOT do any math, DO NOT use asterisks or bullets, and ALWAYS prefix each answer with the "
        "correct section header exactly as shown below (colon after each).\n"
        "If you have no findings for a section, write: None found.\n\n"
        "Potential Other MCA's:\n"
        "Main Spending Patterns:\n"
        "Questionable or Non-Business Expenses:\n"
        "Evidence of Commingling of Business/Personal Funds:\n"
        "Other Collector-Relevant Insights:\n\n"
        "Bank Statement Text:\n"
        f"{ocr_text}\n"
    )

    resp2 = _chat_completion(
        api_key=openai_api_key,
        model=_DEF_MODEL,
        messages=[{"role": "user", "content": main_prompt}],
        max_tokens=512,
        temperature=0.1,
    )

    result2: str = ""
    choices2 = getattr(resp2, "choices", None)
    if choices2:
        msg2 = getattr(choices2[0], "message", None)
        if msg2 and hasattr(msg2, "content"):
            result2 = str(msg2.content or "")
    if not result2 and isinstance(resp2, dict) and "choices" in resp2:
        try:
            result2 = resp2["choices"][0]["message"]["content"]
        except Exception:
            result2 = ""
    result2 = clean_for_pdf(result2.strip())

    # Parse the result using section headers
    sections = [
        "Potential Other MCA's:",
        "Main Spending Patterns:",
        "Questionable or Non-Business Expenses:",
        "Evidence of Commingling of Business/Personal Funds:",
        "Other Collector-Relevant Insights:",
    ]
    section_dict: Dict[str, str] = {h: "None found." for h in sections}

    for line in result2.splitlines():
        s = line.strip()
        for h in sections:
            if s.lower().startswith(h.lower()):
                section_dict[h] = s[len(h) :].strip() or "None found."

    # Now output to PDF in correct order
    for i, header in enumerate(section_headers[3:], start=3):
        c.setFont("Helvetica-Bold", 12)
        c.drawString(margin, y, header)
        y -= 18
        c.setFont("Helvetica", 12)
        pdf_section = sections[i - 3]
        content_line = section_dict.get(pdf_section, "None found.")
        for wrapline in wrap_text(content_line, width=90):
            c.drawString(margin, y, wrapline)
            y -= 16
            if y < margin + 48:
                c.showPage()
                y = height - margin
                c.setFont("Helvetica", 12)

    c.save()
    return str(summary_path)


def process_bank_statements_ai(
    filepaths: Iterable[str], openai_api_key: str, content_frame=None
) -> None:
    for pdf_path in filepaths:
        subfolder = get_statement_subfolder(pdf_path)
        summary_path = gpt_analyze_bank_statement(pdf_path, openai_api_key, subfolder)

        # UI update (optional)
        if content_frame is not None:
            try:
                from customtkinter import CTkLabel  # only used if available
            except Exception:
                CTkLabel = None

            if CTkLabel is not None:
                for widget in content_frame.winfo_children():
                    widget.destroy()
                CTkLabel(
                    content_frame,
                    text="AI Statement Analysis Complete!",
                    font=("Arial", 22, "bold"),
                    text_color="#0075c6",
                ).pack(pady=(25, 10))
                CTkLabel(
                    content_frame,
                    text=f"Redacted processor pages and summary PDF saved to:\n{subfolder}",
                    font=("Arial", 12),
                    text_color="#333",
                ).pack(pady=(10, 2))
                CTkLabel(
                    content_frame,
                    text=f"Latest summary: {os.path.basename(summary_path)}",
                    font=("Arial", 12),
                    text_color="#555",
                ).pack(anchor="w", padx=30)


if __name__ == "__main__":
    import sys

    try:
        import config

        openai_api_key = getattr(config, "openai_api_key", "")
    except Exception:
        openai_api_key = os.getenv("OPENAI_API_KEY", "")

    files = sys.argv[1:]
    if not files:
        print("Usage: python ai_analysis.py file1.pdf [file2.pdf ...]")
        raise SystemExit(1)

    if not openai_api_key:
        print("Error: OPENAI_API_KEY not set (env var or config.openai_api_key).")
        raise SystemExit(2)

    process_bank_statements_ai(files, openai_api_key)
