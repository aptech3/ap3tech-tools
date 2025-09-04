import os
import re
from typing import List, Tuple, Dict, Optional

import fitz  # PyMuPDF


LABELS = {
    "ein": [
        r"\bein\b",
        r"\btin\b",
        r"tax id",
        r"federal tax id",
        r"employer identification",
    ],
    "routing": [
        r"routing",
        r"\baba\b",
        r"routing number",
        r"bank routing",
    ],
    "account": [
        r"account number",
        r"acct number",
        r"acct #",
        r"account #",
        r"\bacct\b",
        r"\bdda\b",
        r"checking account",
    ],
}


EIN_PATTERNS = [
    re.compile(r"\b\d{2}-\d{7}\b"),
    re.compile(r"\b\d{9}\b"),  # fallback if dash omitted
]


def _words_by_line(page) -> Dict[Tuple[int, int], List[Tuple[float, float, float, float, str, int, int, int]]]:
    """Group page.get_text('words') by (block_no, line_no)."""
    words = page.get_text("words") or []
    lines: Dict[Tuple[int, int], List[Tuple[float, float, float, float, str, int, int, int]]] = {}
    for w in words:
        # w: x0, y0, x1, y1, text, block_no, line_no, word_no
        key = (w[5], w[6])
        lines.setdefault(key, []).append(w)
    # sort by x for each line
    for k in list(lines.keys()):
        lines[k].sort(key=lambda t: (t[1], t[0]))
    return lines


def _union_rect(rects: List[fitz.Rect]) -> Optional[fitz.Rect]:
    if not rects:
        return None
    r = fitz.Rect(rects[0])
    for rr in rects[1:]:
        r |= rr
    return r


def _contains_digits(s: str, min_digits: int = 1) -> bool:
    return sum(ch.isdigit() for ch in s) >= min_digits


def _match_any(patterns: List[str], text: str) -> bool:
    tl = text.lower()
    return any(re.search(p, tl, re.I) for p in patterns)


def _collect_sensitive_runs(
    line_words: List[Tuple[float, float, float, float, str, int, int, int]],
    label_patterns: List[str],
    min_digits_for_value: int,
    restrict_to_right_of_label: bool = True,
) -> List[fitz.Rect]:
    """Given line words, find sequences of words right of a label that look like values.

    Heuristics:
    - Identify the right-most x1 of any label-match token(s) on the line.
    - Then collect contiguous words to the right containing digits, x, or *.
    """
    # locate label span x1
    x1_label = None
    for w in line_words:
        text = w[4]
        if _match_any(label_patterns, text):
            x1_label = w[2] if x1_label is None else max(x1_label, w[2])
    rects: List[fitz.Rect] = []
    if restrict_to_right_of_label and x1_label is None:
        return rects

    # Collect contiguous numeric-like runs to the right of label
    current_run: List[fitz.Rect] = []
    for w in line_words:
        x0, y0, x1, y1, text = w[0], w[1], w[2], w[3], w[4]
        if restrict_to_right_of_label and x0 <= (x1_label or 0):
            continue
        t = text.strip()
        if not t:
            continue
        token_has_value = _contains_digits(t, min_digits_for_value) or bool(
            re.search(r"[xX\*]{2,}\d{2,}$", t)
        )
        if token_has_value:
            current_run.append(fitz.Rect(x0, y0, x1, y1))
        else:
            if current_run:
                r = _union_rect(current_run)
                if r:
                    rects.append(r)
                current_run = []
    if current_run:
        r = _union_rect(current_run)
        if r:
            rects.append(r)
    return rects


def _collect_ein_rects(line_words: List[Tuple[float, float, float, float, str, int, int, int]]) -> List[fitz.Rect]:
    rects: List[fitz.Rect] = []
    # First try label-guided
    rects.extend(_collect_sensitive_runs(line_words, LABELS["ein"], min_digits_for_value=9))
    if rects:
        return rects
    # Fallback: any EIN-looking token anywhere on the line
    for w in line_words:
        text = w[4]
        if any(p.search(text) for p in EIN_PATTERNS):
            rects.append(fitz.Rect(w[0], w[1], w[2], w[3]))
    return rects


def _collect_bank_rects(line_words: List[Tuple[float, float, float, float, str, int, int, int]]) -> List[fitz.Rect]:
    rects: List[fitz.Rect] = []
    # Routing numbers (typically 9 digits)
    rects.extend(_collect_sensitive_runs(line_words, LABELS["routing"], min_digits_for_value=9))
    # Account numbers (variable length, but ensure >= 4 digits)
    rects.extend(_collect_sensitive_runs(line_words, LABELS["account"], min_digits_for_value=4))
    return rects


def is_mulligan_contract(input_pdf: str, max_pages: int = 8) -> bool:
    """Heuristic: return True if the PDF text mentions 'Mulligan Funding' in the first N pages."""
    doc = fitz.open(input_pdf)
    try:
        pages = min(max_pages, len(doc))
        target = "mulligan funding"
        for i in range(pages):
            text = (doc[i].get_text() or "").lower()
            if target in text:
                return True
        return False
    finally:
        doc.close()


def redact_mulligan_contract(input_pdf: str, output_pdf: Optional[str] = None, page_number: int = 5) -> Dict[str, int]:
    """Redact EIN and bank routing/account numbers on a specific page (default page 5).

    Returns a summary dict: {"page_index": idx, "redactions": count}
    """
    doc = fitz.open(input_pdf)
    try:
        idx = max(0, page_number - 1)
        if idx >= len(doc):
            raise ValueError(f"PDF has only {len(doc)} page(s); page {page_number} not found")
        page = doc[idx]

        lines = _words_by_line(page)
        target_rects: List[fitz.Rect] = []

        # Pass 1: line-guided by labels
        for key, line_words in lines.items():
            # collect EINs
            target_rects.extend(_collect_ein_rects(line_words))
            # collect bank routing / account
            target_rects.extend(_collect_bank_rects(line_words))

        # Deduplicate overlapping rects
        merged: List[fitz.Rect] = []
        for r in target_rects:
            placed = False
            for i, mr in enumerate(merged):
                if mr.intersects(r) or mr.contains(r) or r.contains(mr):
                    merged[i] = mr | r
                    placed = True
                    break
            if not placed:
                merged.append(r)

        # Add redactions
        for r in merged:
            page.add_redact_annot(r, fill=(0, 0, 0))
        if merged:
            page.apply_redactions()

        # Save
        if not output_pdf:
            root, ext = os.path.splitext(input_pdf)
            output_pdf = f"{root} - Redacted{ext}"
        doc.save(output_pdf)
        return {"page_index": idx, "redactions": len(merged)}
    finally:
        doc.close()


def redact_if_mulligan(input_pdf: str, output_pdf: Optional[str] = None, page_number: int = 5) -> Optional[Dict[str, int]]:
    """If the given PDF appears to be a Mulligan Funding contract, redact the target page.

    Returns summary dict if redacted, otherwise None.
    """
    if is_mulligan_contract(input_pdf):
        return redact_mulligan_contract(input_pdf, output_pdf=output_pdf, page_number=page_number)
    return None


# ---------------- CLI ----------------
def main(argv=None):
    import argparse
    parser = argparse.ArgumentParser(
        prog="contract-redactor",
        description="Redact EIN and bank routing/account numbers on page 5 of Mulligan contracts.",
    )
    parser.add_argument("inputs", nargs="+", help="PDF file(s) to redact")
    parser.add_argument("-p", "--page", type=int, default=5, help="1-based page number (default: 5)")
    parser.add_argument("-o", "--output-dir", default=None, help="Directory to write redacted files (defaults beside input)")
    parser.add_argument("-q", "--quiet", action="store_true", help="Suppress per-file logs")
    args = parser.parse_args(argv)

    ok = 0
    fail = 0
    for inp in args.inputs:
        try:
            if not os.path.isfile(inp):
                raise FileNotFoundError(inp)
            if args.output_dir:
                os.makedirs(args.output_dir, exist_ok=True)
                base = os.path.basename(inp)
                name, ext = os.path.splitext(base)
                out = os.path.join(args.output_dir, f"{name} - Redacted{ext}")
            else:
                out = None
            summary = redact_mulligan_contract(inp, output_pdf=out, page_number=args.page)
            ok += 1
            if not args.quiet:
                print(f"✔ {inp} -> redactions={summary['redactions']} (page index {summary['page_index']})")
        except Exception as e:
            fail += 1
            print(f"✖ {inp}: {e}")
    return 0 if fail == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
