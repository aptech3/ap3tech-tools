import os
import re
import PyPDF2
import customtkinter as ctk
import bsa_settings  # <-- This imports your DB logic!
from thefuzz import fuzz

def process_bank_statements(filepaths, content_frame):
    results = []
    merchant_keywords = bsa_settings.get_all_merchants()
    found_new_suggestions = set()  # To avoid duplicates per batch

    for pdf_path in filepaths:
        findings, suggestions = analyze_pdf(pdf_path, merchant_keywords)
        results.append((pdf_path, findings))
        found_new_suggestions.update(suggestions)

    # Log any new suggestions found (so you can review in BSA Settings UI)
    for suggestion, found_in_file in found_new_suggestions:
        bsa_settings.add_suggestion(suggestion, found_in_file)

    # Show results in the content area
    for widget in content_frame.winfo_children():
        widget.destroy()
    label = ctk.CTkLabel(content_frame, text="Bank Statement Analysis Results", font=("Arial", 22, "bold"), text_color="#0075c6")
    label.pack(pady=(25, 10))

    for pdf_path, findings in results:
        ctk.CTkLabel(content_frame, text=os.path.basename(pdf_path), font=("Arial", 14, "bold"), text_color="#222").pack(pady=(10,2))
        if findings:
            for f in findings:
                ctk.CTkLabel(content_frame, text=" - " + f, font=("Arial", 12), text_color="#444").pack(anchor="w", padx=30)
        else:
            ctk.CTkLabel(content_frame, text="No merchant processor deposits found.", font=("Arial", 12, "italic"), text_color="#a00").pack(anchor="w", padx=30)


# Uses fuzzy logic to identify merchant processors and collect suggestions for new ones
def analyze_pdf(pdf_path, merchant_keywords, fuzzy_threshold=80):
    findings = []
    suggestions = set()
    try:
        with open(pdf_path, "rb") as file:
            reader = PyPDF2.PdfReader(file)
            for i, page in enumerate(reader.pages):
                text = page.extract_text()
                if not text:
                    continue
                page_lines = text.splitlines()
                for line in page_lines:
                    line_found = False
                    line_lower = line.lower()
                    for keyword in merchant_keywords:
                        keyword_lower = keyword.lower()
                        # Substring or Fuzzy match
                        if (
                            keyword_lower in line_lower
                            or fuzz.partial_ratio(keyword_lower, line_lower) >= fuzzy_threshold
                            or fuzz.ratio(keyword_lower, line_lower) >= fuzzy_threshold
                        ):
                            findings.append(f"Page {i+1}: {line.strip()}")
                            line_found = True
                            break
                    # If not found, but looks like a merchant deposit, suggest for review!
                    # Here we flag possible merchants if deposit/credit present and contains a capitalized word
                    if (not line_found) and ("deposit" in line_lower or "credit" in line_lower):
                        # Heuristic: Find "Deposit from X" or similar
                        match = re.search(r"deposit (from|by|via)?\s*([\w\s\-\.\*&]+)", line, re.IGNORECASE)
                        if match:
                            possible_merchant = match.group(2).strip()
                            if possible_merchant and len(possible_merchant) > 2:
                                suggestions.add((possible_merchant, os.path.basename(pdf_path)))
    except Exception as e:
        findings.append(f"Error reading PDF: {e}")
    return findings, suggestions

# If you want, you can add:
# - GPT summary integration
# - Redaction logic
# - Highlighting/output PDF generation, etc.
